import itertools, math, random
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.partidos.models import Partido, SetPartido
from app.torneos.models import Categoria, Grupo
from app.equipos.models import Equipo
from app.shared.errors import AppError, NotFound, BadRequest

async def generar_fixture(db: AsyncSession, categoria_id: str) -> list[Partido]:
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no existe", {"id": categoria_id})

    res = await db.execute(select(Equipo).where(Equipo.categoria_id == categoria_id, Equipo.estado == "aprobado"))
    equipos = res.scalars().all()
    if len(equipos) < 2:
        raise AppError(400, "EQUIPOS_INSUFICIENTES", "Se necesitan al menos 2 equipos aprobados", {"count": len(equipos)})

    await db.execute(delete(Partido).where(Partido.categoria_id == categoria_id, Partido.estado == "pendiente"))

    partidos_creados = []

    if cat.formato in ("grupos", "round_robin"):
        n = cat.equipos_x_grupo
        num_grupos = math.ceil(len(equipos) / n)
        res = await db.execute(select(Grupo).where(Grupo.categoria_id == categoria_id))
        grupos = res.scalars().all()
        if len(grupos) != num_grupos:
            await db.execute(delete(Grupo).where(Grupo.categoria_id == categoria_id))
            await db.flush()
            grupos = []
            for i in range(num_grupos):
                g = Grupo(categoria_id=categoria_id, nombre=chr(65+i), orden=i+1)
                db.add(g)
                grupos.append(g)
            await db.flush()

        # Shuffle per category for randomness
        random.seed(str(categoria_id).encode())
        equipos_sorted = sorted(equipos, key=lambda e: e.seed or 999)
        random.shuffle(equipos_sorted)
        for idx, eq in enumerate(equipos_sorted):
            if not eq.grupo_id:
                eq.grupo_id = grupos[idx % num_grupos].id
        await db.flush()

        for grupo in grupos:
            res = await db.execute(select(Equipo).where(Equipo.grupo_id == grupo.id))
            eqs = res.scalars().all()
            for a, b in itertools.combinations(eqs, 2):
                p = Partido(categoria_id=categoria_id, grupo_id=grupo.id, fase="grupos", equipo_local_id=a.id, equipo_visit_id=b.id, estado="pendiente")
                db.add(p)
                partidos_creados.append(p)
        await db.flush()

    elif cat.formato == "eliminatoria":
        if len(equipos) % 2 != 0:
            raise AppError(400, "EQUIPOS_IMPAR", "Formato eliminatoria requiere número par de equipos", {"count": len(equipos)})
        equipos_sorted = sorted(equipos, key=lambda e: e.seed or 999)
        for i in range(0, len(equipos_sorted), 2):
            a = equipos_sorted[i]
            b = equipos_sorted[i+1]
            p = Partido(categoria_id=categoria_id, fase="cuartos" if len(equipos) > 4 else "semi", equipo_local_id=a.id, equipo_visit_id=b.id, estado="pendiente")
            db.add(p)
            partidos_creados.append(p)
        await db.flush()

    await db.flush()
    return partidos_creados

async def programar_partido(db: AsyncSession, partido_id: str, cancha: str = None, fecha_hora=None) -> Partido:
    from uuid import UUID as _UUID
    try:
        _UUID(partido_id)
    except ValueError:
        raise BadRequest("INVALID_UUID", "UUID inválido")
    res = await db.execute(select(Partido).where(Partido.id == partido_id))
    partido = res.scalar_one_or_none()
    if not partido:
        raise NotFound("PARTIDO_NOT_FOUND", "Partido no existe", {"id": partido_id})
    if partido.estado == "finalizado":
        raise AppError(400, "PARTIDO_YA_FINALIZADO", "No se puede reprogramar un partido finalizado")
    if cancha is not None and len(cancha) > 50:
        raise AppError(400, "CANCHA_TOO_LONG", "Cancha máx 50 caracteres")
    if cancha is not None:
        partido.cancha = cancha
    if fecha_hora is not None:
        partido.fecha_hora = fecha_hora
    await db.flush()
    return partido

async def registrar_resultado(db: AsyncSession, partido_id: str, sets: list) -> Partido:
    res = await db.execute(select(Partido).where(Partido.id == partido_id))
    partido = res.scalar_one_or_none()
    if not partido:
        raise NotFound("PARTIDO_NOT_FOUND", "Partido no existe", {"id": partido_id})
    if partido.estado == "finalizado":
        raise AppError(400, "PARTIDO_YA_FINALIZADO", "Partido ya finalizado")

    res2 = await db.execute(select(Categoria).where(Categoria.id == partido.categoria_id))
    cat = res2.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no encontrada")

    sets_needed = (cat.sets_x_partido // 2) + 1

    # Validate number of sets
    if len(sets) < sets_needed:
        raise AppError(400, "SETS_INSUFICIENTES", f"Se necesitan al menos {sets_needed} sets para determinar ganador")

    # Validate sequential numbering and no duplicates
    numeros = [s["numero_set"] for s in sets]
    if sorted(numeros) != list(range(1, len(sets) + 1)):
        raise AppError(400, "NUMERO_SET_INVALIDO", "Los sets deben ser numerados secuencialmente desde 1")

    # Validate pts >= 15/21/25 and difference >= 2
    for s in sets:
        winner_pts = max(s["pts_local"], s["pts_visitante"])
        loser_pts = min(s["pts_local"], s["pts_visitante"])
        if s["pts_local"] == s["pts_visitante"]:
            raise AppError(400, "SET_EMPATE", "Set no puede empatar")
        if winner_pts < cat.puntos_x_set:
            raise AppError(400, "PTS_INSUFICIENTES", f"Set requiere mínimo {cat.puntos_x_set} puntos")
        if winner_pts - loser_pts < 2:
            raise AppError(400, "PTS_DIFERENCIA", "Ganador debe tener al menos 2 puntos de diferencia")

    # Upsert sets (don't delete history)
    from sqlalchemy import text as sa_text
    for s in sets:
        ganador = partido.equipo_local_id if s["pts_local"] > s["pts_visitante"] else partido.equipo_visit_id
        res3 = await db.execute(select(SetPartido).where(SetPartido.partido_id == partido_id, SetPartido.numero_set == s["numero_set"]))
        existing = res3.scalar_one_or_none()
        if existing:
            existing.pts_local = s["pts_local"]
            existing.pts_visitante = s["pts_visitante"]
            existing.ganador_id = ganador
            existing.duracion_min = s.get("duracion_min")
        else:
            sp = SetPartido(partido_id=partido_id, numero_set=s["numero_set"], pts_local=s["pts_local"], pts_visitante=s["pts_visitante"], ganador_id=ganador, duracion_min=s.get("duracion_min"))
            db.add(sp)

    # Determine match winner
    wins_local = sum(1 for s in sets if s["pts_local"] > s["pts_visitante"])
    wins_visit = len(sets) - wins_local

    if wins_local >= sets_needed:
        partido.ganador_id = partido.equipo_local_id
    elif wins_visit >= sets_needed:
        partido.ganador_id = partido.equipo_visit_id
    else:
        raise AppError(400, "SETS_INSUFICIENTES", f"Se necesitan {sets_needed} sets ganados", {"wins_local": wins_local, "wins_visit": wins_visit})

    partido.estado = "finalizado"
    await db.flush()
    return partido

async def list_partidos(db: AsyncSession, torneo_id: str = None, categoria_id: str = None, grupo_id: str = None, fase: str = None):
    query = select(Partido)
    if categoria_id:
        query = query.where(Partido.categoria_id == categoria_id)
    elif torneo_id:
        from app.torneos.models import Categoria, Rama
        query = query.join(Categoria, Partido.categoria_id == Categoria.id).join(Rama, Categoria.rama_id == Rama.id).where(Rama.torneo_id == torneo_id)
    if grupo_id:
        query = query.where(Partido.grupo_id == grupo_id)
    if fase:
        query = query.where(Partido.fase == fase)
    query = query.order_by(Partido.fecha_hora)
    res = await db.execute(query)
    return res.scalars().all()

async def get_partido(db: AsyncSession, partido_id: str) -> tuple[Partido, list[SetPartido]]:
    res = await db.execute(select(Partido).where(Partido.id == partido_id))
    partido = res.scalar_one_or_none()
    if not partido:
        raise NotFound("PARTIDO_NOT_FOUND", "Partido no existe", {"id": partido_id})
    res2 = await db.execute(select(SetPartido).where(SetPartido.partido_id == partido_id).order_by(SetPartido.numero_set))
    sets = res2.scalars().all()
    return partido, sets
