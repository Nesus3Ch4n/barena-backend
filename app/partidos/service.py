import uuid, itertools, math, random
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.partidos.models import Partido, SetPartido
from app.torneos.models import Categoria, Grupo
from app.equipos.models import Equipo
from app.shared.errors import AppError, NotFound

async def generar_fixture(db: AsyncSession, categoria_id: str) -> list[Partido]:
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no existe", {"id": categoria_id})

    # Fetch equipos aprobados
    res = await db.execute(select(Equipo).where(Equipo.categoria_id == categoria_id, Equipo.estado == "aprobado"))
    equipos = res.scalars().all()
    if len(equipos) < 2:
        raise AppError(400, "EQUIPOS_INSUFICIENTES", "Se necesitan al menos 2 equipos aprobados", {"count": len(equipos)})

    # Clear existing partidos pendientes for this categoria? Only if not finalizados
    await db.execute(delete(Partido).where(Partido.categoria_id == categoria_id, Partido.estado == "pendiente"))

    partidos_creados = []

    if cat.formato in ("grupos", "round_robin"):
        # Crear grupos si no existen o recrear
        n = cat.equipos_x_grupo
        num_grupos = math.ceil(len(equipos) / n)
        # fetch existing grupos
        res = await db.execute(select(Grupo).where(Grupo.categoria_id == categoria_id))
        grupos = res.scalars().all()
        # si no hay grupos o num difiere, recrear
        if len(grupos) != num_grupos:
            await db.execute(delete(Grupo).where(Grupo.categoria_id == categoria_id))
            await db.flush()
            grupos = []
            for i in range(num_grupos):
                g = Grupo(categoria_id=categoria_id, nombre=chr(65+i), orden=i+1)
                db.add(g)
                grupos.append(g)
            await db.flush()

        # Asignar equipos a grupos (si aún no tienen grupo) round-robin por orden
        random.seed(42)  # deterministico para MVP
        equipos_sorted = sorted(equipos, key=lambda e: e.seed or 999)
        for idx, eq in enumerate(equipos_sorted):
            if not eq.grupo_id:
                eq.grupo_id = grupos[idx % num_grupos].id
        await db.flush()

        # Re-fetch grupos con equipos
        for grupo in grupos:
            res = await db.execute(select(Equipo).where(Equipo.grupo_id == grupo.id))
            eqs = res.scalars().all()
            # round robin all vs all
            for a, b in itertools.combinations(eqs, 2):
                p = Partido(categoria_id=categoria_id, grupo_id=grupo.id, fase="grupos", equipo_local_id=a.id, equipo_visit_id=b.id, estado="pendiente")
                db.add(p)
                partidos_creados.append(p)
        await db.flush()

        # Si formato grupos y avance configurado, no generamos eliminatoria aún (se genera tras fase grupos)
    elif cat.formato == "eliminatoria":
        # Single elimination bracket
        # shuffle by seed
        equipos_sorted = sorted(equipos, key=lambda e: e.seed or 999)
        # pad to power of 2? simple pair sequencial
        for i in range(0, len(equipos_sorted) - 1, 2):
            a = equipos_sorted[i]
            b = equipos_sorted[i+1] if i+1 < len(equipos_sorted) else None
            if not b:
                # bye
                continue
            p = Partido(categoria_id=categoria_id, fase="cuartos" if len(equipos) > 4 else "semi", equipo_local_id=a.id, equipo_visit_id=b.id, estado="pendiente")
            db.add(p)
            partidos_creados.append(p)
        await db.flush()
    else:  # custom
        pass

    await db.flush()
    return partidos_creados

async def programar_partido(db: AsyncSession, partido_id: str, cancha: str = None, fecha_hora=None) -> Partido:
    res = await db.execute(select(Partido).where(Partido.id == partido_id))
    partido = res.scalar_one_or_none()
    if not partido:
        raise NotFound("PARTIDO_NOT_FOUND", "Partido no existe", {"id": partido_id})
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

    # fetch categoria for sets_x_partido
    res2 = await db.execute(select(Categoria).where(Categoria.id == partido.categoria_id))
    cat = res2.scalar_one_or_none()
    sets_needed = (cat.sets_x_partido // 2) + 1 if cat else 2

    # Clear existing sets for partido
    await db.execute(delete(SetPartido).where(SetPartido.partido_id == partido_id))

    wins_local = 0
    wins_visit = 0
    for s in sets:
        if s["pts_local"] == s["pts_visitante"]:
            raise AppError(400, "SET_EMPATE", "Set no puede empatar")
        ganador = partido.equipo_local_id if s["pts_local"] > s["pts_visitante"] else partido.equipo_visit_id
        if s["pts_local"] > s["pts_visitante"]:
            wins_local += 1
        else:
            wins_visit += 1
        sp = SetPartido(partido_id=partido_id, numero_set=s["numero_set"], pts_local=s["pts_local"], pts_visitante=s["pts_visitante"], ganador_id=ganador, duracion_min=s.get("duracion_min"))
        db.add(sp)

    # ganador partido
    if wins_local >= sets_needed:
        partido.ganador_id = partido.equipo_local_id
    elif wins_visit >= sets_needed:
        partido.ganador_id = partido.equipo_visit_id
    else:
        raise AppError(400, "SETS_INSUFICIENTES", f"Se necesitan {sets_needed} sets ganados para ganar partido", {"wins_local": wins_local, "wins_visit": wins_visit})

    partido.estado = "finalizado"
    await db.flush()

    # Set app.current_user_id for RLS trigger? Already handled by DB triggers which recompute rankings via trigger
    # Also ensure rankings are recalculated via triggers (they fire on partidos update and sets insert)
    # For fallback if triggers not yet migrated, we can call functions manually? But they exist in DB

    return partido

async def list_partidos(db: AsyncSession, torneo_id: str = None, categoria_id: str = None, grupo_id: str = None, fase: str = None):
    query = select(Partido)
    if categoria_id:
        query = query.where(Partido.categoria_id == categoria_id)
    elif torneo_id:
        # need join categoria -> rama -> torneo
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
