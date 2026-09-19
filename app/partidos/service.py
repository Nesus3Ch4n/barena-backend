import itertools, math, random
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc
from app.partidos.models import Partido, SetPartido, PartidoEvento
from app.torneos.models import Categoria, Grupo, Rama
from app.equipos.models import Equipo
from app.atletas.models import Atleta
from app.shared.errors import AppError, NotFound, BadRequest

# Fase que le sigue a cada fase de eliminación directa (auto-avance del ganador).
NEXT_FASE = {
    "treintaidosavos": "dieciseisavos",
    "dieciseisavos": "octavos",
    "octavos": "cuartos",
    "cuartos": "semi",
    "semi": "final",
    "final": None,
    "tercer_puesto": None,
}
# Fases de eliminación directa (perdedores de semi pasan a 3er puesto).
FASES_ELIMINATORIA = ["treintaidosavos", "dieciseisavos", "octavos", "cuartos", "semi", "final", "tercer_puesto"]
# Nombre de fase según cantidad de llaves de ese nivel (m = llaves).
FASE_POR_LLAVES = {1: "final", 2: "semi", 4: "cuartos", 8: "octavos", 16: "dieciseisavos", 32: "treintaidosavos"}

def _es_potencia_de_2(n):
    return n != 0 and (n & (n - 1)) == 0

def _siguiente_pot2(n):
    p = 1
    while p < max(n, 2):
        p <<= 1
    return p

def _seats_por_seed(n):
    """Devuelve la lista de asientos (1-based) por seed para armar una llave
    balanceada: seed 1 y 2 nunca chocan antes de la final."""
    seats = [1]
    while len(seats) < n:
        prev = list(seats)
        seats = [2 * x for x in prev] + [2 * x - 1 for x in reversed(prev)]
    return seats

def _fase_de_llaves(m):
    return FASE_POR_LLAVES.get(m, "ronda")

async def generar_fixture(db: AsyncSession, categoria_id: str, bracket_tipo: str = None, crear_grupos: bool = True, sincronizar_grupos: bool = False) -> list[Partido]:
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no existe", {"id": categoria_id})

    res = await db.execute(select(Equipo).where(Equipo.categoria_id == categoria_id, Equipo.estado == "aprobado"))
    equipos = res.scalars().all()
    if len(equipos) < 2:
        raise AppError(400, "EQUIPOS_INSUFICIENTES", "Se necesitan al menos 2 equipos aprobados", {"count": len(equipos)})

    # bracket_tipo override or from categoria
    efectivo_bracket = bracket_tipo or getattr(cat, "bracket_tipo", "general") or "general"
    if efectivo_bracket not in ("general", "diamante", "oro", "diamante_oro"):
        efectivo_bracket = "general"

    await db.execute(delete(Partido).where(Partido.categoria_id == categoria_id, Partido.estado == "pendiente"))

    partidos_creados = []

    def _pair_and_create(eqs_sorted, btype):
        # 1 vs last, 2 vs penultimo...
        n = len(eqs_sorted)
        fase = "cuartos" if n > 4 else "semi" if n > 2 else "final"
        for i in range(n // 2):
            a = eqs_sorted[i]
            b = eqs_sorted[n - 1 - i]
            p = Partido(categoria_id=categoria_id, fase=fase, equipo_local_id=a.id, equipo_visit_id=b.id, estado="pendiente", bracket_tipo=btype, orden_en_round=i)
            db.add(p)
            partidos_creados.append(p)

    if cat.formato in ("grupos", "round_robin"):
        n = cat.equipos_x_grupo
        num_grupos = math.ceil(len(equipos) / n)
        res = await db.execute(select(Grupo).where(Grupo.categoria_id == categoria_id))
        grupos = list(res.scalars().all())
        if sincronizar_grupos or (crear_grupos and len(grupos) != num_grupos):
            # Sync total: elimina grupos sobrantes con sus partidos pendientes,
            # crea los faltantes y reasigna equipos huerfanos.
            if sincronizar_grupos and len(grupos) > num_grupos:
                sobrantes = sorted(grupos, key=lambda g: g.orden or 0)[num_grupos:]
                for g in sobrantes:
                    res_p = await db.execute(select(Partido).where(Partido.grupo_id == g.id, Partido.estado != "pendiente"))
                    if res_p.scalars().first():
                        raise AppError(400, "GRUPO_CON_PARTIDOS", "El grupo tiene partidos en juego o finalizados", {"grupo": g.nombre})
                    await db.execute(delete(Partido).where(Partido.grupo_id == g.id))
                    res_eq = await db.execute(select(Equipo).where(Equipo.grupo_id == g.id))
                    for eq in res_eq.scalars().all():
                        eq.grupo_id = None
                    await db.delete(g)
                await db.flush()
                res = await db.execute(select(Grupo).where(Grupo.categoria_id == categoria_id).order_by(Grupo.orden))
                grupos = list(res.scalars().all())
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
                p = Partido(categoria_id=categoria_id, grupo_id=grupo.id, fase="grupos", equipo_local_id=a.id, equipo_visit_id=b.id, estado="pendiente", bracket_tipo="general")
                db.add(p)
                partidos_creados.append(p)
        await db.flush()

    elif cat.formato == "eliminatoria":
        if len(equipos) % 2 != 0:
            raise AppError(400, "EQUIPOS_IMPAR", "Formato eliminatoria requiere número par de equipos", {"count": len(equipos)})
        equipos_sorted = sorted(equipos, key=lambda e: e.seed or 999)
        # diamante/oro split
        if efectivo_bracket == "diamante_oro":
            mid = (len(equipos_sorted) + 1) // 2
            diamante = equipos_sorted[:mid]
            oro = equipos_sorted[mid:]
            _pair_and_create(diamante, "diamante")
            _pair_and_create(oro, "oro")
        elif efectivo_bracket == "diamante":
            mid = (len(equipos_sorted) + 1) // 2
            diamante = equipos_sorted[:mid]
            if len(diamante) % 2 != 0:
                raise AppError(400, "EQUIPOS_IMPAR", "Diamante requiere número par", {"count": len(diamante)})
            _pair_and_create(diamante, "diamante")
        elif efectivo_bracket == "oro":
            mid = (len(equipos_sorted) + 1) // 2
            oro = equipos_sorted[mid:]
            if len(oro) % 2 != 0:
                raise AppError(400, "EQUIPOS_IMPAR", "Oro requiere número par", {"count": len(oro)})
            _pair_and_create(oro, "oro")
        else:  # general
            _pair_and_create(equipos_sorted, "general")
        await db.flush()

    await db.flush()
    return partidos_creados

async def actualizar_grupo(db: AsyncSession, grupo_id: str, data: dict) -> Grupo:
    res = await db.execute(select(Grupo).where(Grupo.id == grupo_id))
    grupo = res.scalar_one_or_none()
    if not grupo:
        raise NotFound("GRUPO_NOT_FOUND", "Grupo no existe", {"id": grupo_id})
    if data.get("nombre"):
        nombre = data["nombre"].strip().upper()[:10]
        res2 = await db.execute(select(Grupo).where(Grupo.categoria_id == grupo.categoria_id, Grupo.nombre == nombre, Grupo.id != grupo_id))
        if res2.scalar_one_or_none():
            raise AppError(400, "GRUPO_DUPLICADO", "Ya existe un grupo con ese nombre", {"nombre": nombre})
        grupo.nombre = nombre
    if data.get("orden") is not None:
        grupo.orden = data["orden"]
    await db.flush()
    return grupo

async def eliminar_grupo(db: AsyncSession, grupo_id: str) -> None:
    res = await db.execute(select(Grupo).where(Grupo.id == grupo_id))
    grupo = res.scalar_one_or_none()
    if not grupo:
        raise NotFound("GRUPO_NOT_FOUND", "Grupo no existe", {"id": grupo_id})
    res_p = await db.execute(select(Partido).where(Partido.grupo_id == grupo_id, Partido.estado != "pendiente"))
    if res_p.scalars().first():
        raise AppError(400, "GRUPO_CON_PARTIDOS", "El grupo tiene partidos en juego o finalizados", {"grupo": grupo.nombre})
    await db.execute(delete(Partido).where(Partido.grupo_id == grupo_id))
    res_eq = await db.execute(select(Equipo).where(Equipo.grupo_id == grupo_id))
    for eq in res_eq.scalars().all():
        eq.grupo_id = None
    await db.delete(grupo)
    await db.flush()

async def borrar_partidos_fase_grupos(db: AsyncSession, categoria_id: str) -> int:
    """Elimina todos los partidos de la fase de grupos de una categoría."""
    res = await db.execute(select(Partido).where(Partido.categoria_id == categoria_id, Partido.fase == "grupos"))
    ids = [p.id for p in res.scalars().all()]
    if ids:
        await db.execute(delete(Partido).where(Partido.id.in_(ids)))
        await db.flush()
    return len(ids)

async def generar_bracket_desde_ranking(db: AsyncSession, categoria_id: str) -> list[Partido]:
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no existe", {"id": categoria_id})

    clasificacion = getattr(cat, "clasificacion", "grupos") or "grupos"
    clasificados = []

    if clasificacion == "ranking_general":
        # Todas las duplas aprobadas, ordenadas por ranking general (primero
        # las posicionadas, después el resto por nombre).
        from app.rankings.models import RankingGeneral
        ranked_pos = {}
        res = await db.execute(
            select(RankingGeneral).where(RankingGeneral.categoria_id == categoria_id).order_by(RankingGeneral.posicion)
        )
        for r in res.scalars().all():
            ranked_pos[r.equipo_id] = r.posicion
        res = await db.execute(select(Equipo).where(Equipo.categoria_id == categoria_id, Equipo.estado == "aprobado"))
        equipos = res.scalars().all()
        clasificados = sorted(equipos, key=lambda e: (ranked_pos.get(e.id, 10 ** 9), e.nombre))
    else:
        # Clasificación por grupos: los avance_x_grupo primeros de cada grupo.
        res = await db.execute(select(Grupo).where(Grupo.categoria_id == categoria_id).order_by(Grupo.orden))
        grupos = res.scalars().all()
        if not grupos:
            raise AppError(400, "SIN_GRUPOS", "No hay grupos en la categoria")
        from app.rankings.models import RankingGrupo
        for grupo in grupos:
            res = await db.execute(
                select(RankingGrupo).where(RankingGrupo.grupo_id == grupo.id).order_by(RankingGrupo.posicion)
            )
            ranks = res.scalars().all()
            for r in ranks[: cat.avance_x_grupo]:
                eq_res = await db.execute(select(Equipo).where(Equipo.id == r.equipo_id))
                eq = eq_res.scalar_one_or_none()
                if eq:
                    clasificados.append(eq)

    if len(clasificados) < 2:
        raise AppError(400, "CLASIFICADOS_INSUFICIENTES", "Se necesitan al menos 2 clasificados", {"count": len(clasificados)})

    efectivo_bracket = getattr(cat, "bracket_tipo", "general") or "general"
# Borrar llaves pendientes previas para regenerar desde cero.
    await db.execute(delete(Partido).where(Partido.categoria_id == categoria_id, Partido.fase.in_(FASES_ELIMINATORIA), Partido.estado == "pendiente"))
    await db.flush()

    partidos_creados: list[Partido] = []

    async def _crear_ladder_para(eqs, btype):
        B = _siguiente_pot2(len(eqs))
        seats = _seats_por_seed(B)
        slots = [None] * B
        for idx, team in enumerate(eqs):
            pos = seats[idx] - 1
            if 0 <= pos < B:
                slots[pos] = team.id
        await _armar_ladder(db, categoria_id, slots, btype, partidos_creados)

    if efectivo_bracket == "diamante_oro":
        mid = (len(clasificados) + 1) // 2
        await _crear_ladder_para(clasificados[:mid], "diamante")
        await _crear_ladder_para(clasificados[mid:], "oro")
    elif efectivo_bracket == "diamante":
        await _crear_ladder_para(clasificados[: (len(clasificados) + 1) // 2], "diamante")
    elif efectivo_bracket == "oro":
        await _crear_ladder_para(clasificados[(len(clasificados) + 1) // 2 :], "oro")
    else:
        await _crear_ladder_para(clasificados, "general")

    await db.flush()
    return partidos_creados

async def _armar_ladder(db, categoria_id, slots, btype, partidos_creados):
    """Construye la escala completa: la llave j de una fase alimenta la llave j//2
    de la siguiente (local si j par, visitante si j impar). Los byes de la ronda
    inicial avanzan directo y los partidos sin participantes conocidos se crean
    sobre la marcha cuando completa (final y 3er puesto nacen vacíos)."""
    from app.partidos.models import Partido as _P
    res = await db.execute(
        select(_P).where(
            _P.categoria_id == categoria_id,
            _P.fase.in_(FASES_ELIMINATORIA),
            _P.estado == "finalizado",
        )
    )
    finalizados = {(p.fase, p.llave, p.bracket_tipo) for p in res.scalars().all()}
    B = len(slots)
    niveles = B.bit_length() - 1
    cur = slots
    for level in range(niveles):
        m = B >> (level + 1)
        nxt = [None] * m
        fase = _fase_de_llaves(m)
        for j in range(m):
            a = cur[2 * j]
            b = cur[2 * j + 1]
            if (fase, j, btype) in finalizados:
                continue
            if a is not None and b is not None:
                p = Partido(categoria_id=categoria_id, fase=fase, llave=j, equipo_local_id=a, equipo_visit_id=b, estado="pendiente", bracket_tipo=btype)
                db.add(p)
                partidos_creados.append(p)
            elif a is None and b is None:
                continue
            elif level == 0:
                # bye en la ronda inicial: el clasificado pasa directo a la siguiente ronda
                nxt[j] = a if a is not None else b
            else:
                # nivel interno con un solo lado conocido: crea la llave, el ganador de la rama contraria la completa
                p = Partido(categoria_id=categoria_id, fase=fase, llave=j, equipo_local_id=a, equipo_visit_id=b, estado="pendiente", bracket_tipo=btype)
                db.add(p)
                partidos_creados.append(p)
        cur = nxt

async def _avanzar_ganador(db: AsyncSession, partido: Partido):
    """Auto-avance: al finalizar un partido de eliminación directa, el ganador
    ocupa el asiento libre de la llave siguiente (llave j -> llave j//2, local
    si j es par, visitante si es impar). Los perdedores de las semis van al 3er
    puesto."""
    if not partido.ganador_id or partido.estado != "finalizado":
        return
    if partido.fase not in NEXT_FASE or NEXT_FASE[partido.fase] is None:
        return
    llave = partido.llave or 0

    if partido.fase == "semi":
        if llave not in (0, 1):
            return
        res = await db.execute(
            select(Partido).where(
                Partido.categoria_id == partido.categoria_id,
                Partido.fase == "semi",
                Partido.llave == (1 - llave),
            )
        )
        gemela = res.scalar_one_or_none()
        # solo tiene sentido el 3er puesto si la semi gemela es un partido real
        if not gemela or not gemela.equipo_local_id or not gemela.equipo_visit_id:
            return
        perdedor = partido.equipo_visit_id if partido.ganador_id == partido.equipo_local_id else partido.equipo_local_id
        res2 = await db.execute(
            select(Partido).where(
                Partido.categoria_id == partido.categoria_id,
                Partido.fase == "tercer_puesto",
                Partido.bracket_tipo == partido.bracket_tipo,
            )
        )
        tercer = res2.scalars().first()
        if not tercer:
            tercer = Partido(categoria_id=partido.categoria_id, fase="tercer_puesto", llave=0, equipo_local_id=None, equipo_visit_id=None, estado="pendiente", bracket_tipo=partido.bracket_tipo)
            db.add(tercer)
        if llave % 2 == 0:
            if tercer.equipo_local_id is None:
                tercer.equipo_local_id = perdedor
        else:
            if tercer.equipo_visit_id is None:
                tercer.equipo_visit_id = perdedor
        await db.flush()
        return

    next_fase = NEXT_FASE[partido.fase]
    next_llave = llave // 2
    res = await db.execute(
        select(Partido).where(
            Partido.categoria_id == partido.categoria_id,
            Partido.fase == next_fase,
            Partido.llave == next_llave,
            Partido.bracket_tipo == partido.bracket_tipo,
        )
    )
    siguiente = res.scalar_one_or_none()
    if not siguiente:
        siguiente = Partido(categoria_id=partido.categoria_id, fase=next_fase, llave=next_llave, equipo_local_id=None, equipo_visit_id=None, estado="pendiente", bracket_tipo=partido.bracket_tipo)
        db.add(siguiente)
    if llave % 2 == 0:
        if siguiente.equipo_local_id is None:
            siguiente.equipo_local_id = partido.ganador_id
    else:
        if siguiente.equipo_visit_id is None:
            siguiente.equipo_visit_id = partido.ganador_id
    await db.flush()

async def programar_partido(db: AsyncSession, partido_id: str, cancha: str = None, fecha_hora=None, is_organizador: bool = False) -> Partido:
    from uuid import UUID as _UUID
    try:
        _UUID(partido_id)
    except ValueError:
        raise BadRequest("INVALID_UUID", "UUID inválido")
    res = await db.execute(select(Partido).where(Partido.id == partido_id))
    partido = res.scalar_one_or_none()
    if not partido:
        raise NotFound("PARTIDO_NOT_FOUND", "Partido no existe", {"id": partido_id})
    if partido.estado == "finalizado" and not is_organizador:
        raise AppError(400, "PARTIDO_YA_FINALIZADO", "No se puede reprogramar un partido finalizado - solo organizador")
    if cancha is not None and len(cancha) > 50:
        raise AppError(400, "CANCHA_TOO_LONG", "Cancha máx 50 caracteres")
    if cancha is not None:
        partido.cancha = cancha
    if fecha_hora is not None:
        partido.fecha_hora = fecha_hora
    await db.flush()
    return partido

async def registrar_resultado(db: AsyncSession, partido_id: str, sets: list, is_organizador: bool = False, tarjetas: dict = None) -> Partido:
    res = await db.execute(select(Partido).where(Partido.id == partido_id))
    partido = res.scalar_one_or_none()
    if not partido:
        raise NotFound("PARTIDO_NOT_FOUND", "Partido no existe", {"id": partido_id})
    if partido.estado == "finalizado" and not is_organizador:
        raise AppError(400, "PARTIDO_YA_FINALIZADO", "Partido ya finalizado - solo organizador puede editar")

    tarjetas = tarjetas or {}
    if tarjetas:
        for k in ["tarjetas_amarillas_local", "tarjetas_rojas_local", "tarjetas_amarillas_visit", "tarjetas_rojas_visit"]:
            setattr(partido, k, max(0, int(tarjetas.get(k, 0))))

    res2 = await db.execute(select(Categoria).where(Categoria.id == partido.categoria_id))
    cat = res2.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no encontrada")

    # 2-set: tope = puntos_x_set elegido (15 o 21) sin alargues
    if cat.sets_x_partido == 2:
        if len(sets) != 2:
            raise AppError(400, "SETS_INVALIDOS", "Formato 2 sets requiere exactamente 2 sets")
        numeros = [s["numero_set"] for s in sets]
        if sorted(numeros) != [1, 2]:
            raise AppError(400, "NUMERO_SET_INVALIDO", "Sets deben ser 1 y 2")
        cap = cat.puntos_x_set
        requiere2 = getattr(cat, "diferencia_dos_puntos", True)
        for s in sets:
            w = max(s["pts_local"], s["pts_visitante"])
            l = min(s["pts_local"], s["pts_visitante"])
            if s["pts_local"] == s["pts_visitante"]:
                raise AppError(400, "SET_EMPATE", "Set no puede empatar")
            if w != cap:
                raise AppError(400, "PTS_TOPE", f"Set {s['numero_set']} tope {cap}: ganador debe tener {cap} (sin alargues)")
            if requiere2 and w - l < 2:
                raise AppError(400, "PTS_DIFERENCIA", f"Set {s['numero_set']} a {cap} requiere ventaja de 2 ({cap}-{cap-1} no termina, {cap}-{cap-2} sí)")
            if w > cap or l >= cap:
                raise AppError(400, "PTS_TOPE", f"Tope máximo {cap}")
        # Upsert
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
        wins_local = sum(1 for s in sets if s["pts_local"] > s["pts_visitante"])
        wins_visit = 2 - wins_local
        total_local = sum(s["pts_local"] for s in sets)
        total_visit = sum(s["pts_visitante"] for s in sets)
        if wins_local == 2:
            partido.ganador_id = partido.equipo_local_id
        elif wins_visit == 2:
            partido.ganador_id = partido.equipo_visit_id
        elif wins_local == 1 and wins_visit == 1:
            if total_local > total_visit:
                partido.ganador_id = partido.equipo_local_id
            elif total_visit > total_local:
                partido.ganador_id = partido.equipo_visit_id
            else:
                # punto de oro / empate: sin ganador, ambos 2 pts
                partido.ganador_id = None
        else:
            raise AppError(400, "SETS_INVALIDOS", "Estado inválido para 2 sets")
        partido.estado = "finalizado"
        await db.flush()
        await _avanzar_ganador(db, partido)
        return partido

    sets_needed = (cat.sets_x_partido // 2) + 1

    # Validate number of sets
    if len(sets) < sets_needed:
        raise AppError(400, "SETS_INSUFICIENTES", f"Se necesitan al menos {sets_needed} sets para determinar ganador")

    # Validate sequential numbering and no duplicates
    numeros = [s["numero_set"] for s in sets]
    if sorted(numeros) != list(range(1, len(sets) + 1)):
        raise AppError(400, "NUMERO_SET_INVALIDO", "Los sets deben ser numerados secuencialmente desde 1")

    # Validate pts >= 15/21/25 and diferencia de 2 (según termino voleibol)
    # En voleibol, el set decisivo (último) se juega a 15 si el formato es a 3 o 5 sets
    def _puntos_requeridos(num_set: int) -> int:
        # Si es el set decisivo y formato es mejor de 3 o 5, el último set es a 15
        if cat.sets_x_partido in (3, 5) and num_set == cat.sets_x_partido:
            return 15
        return cat.puntos_x_set
    for s in sets:
        req = _puntos_requeridos(s["numero_set"])
        winner_pts = max(s["pts_local"], s["pts_visitante"])
        loser_pts = min(s["pts_local"], s["pts_visitante"])
        if s["pts_local"] == s["pts_visitante"]:
            raise AppError(400, "SET_EMPATE", "Set no puede empatar")
        # sin alargues: tope es lo elegido (15 o 21)
        if winner_pts != req:
            raise AppError(400, "PTS_TOPE", f"Set {s['numero_set']} tope {req}: ganador debe tener {req} (sin alargues)")
        if winner_pts > req or loser_pts >= req:
            raise AppError(400, "PTS_TOPE", f"Tope máximo {req}")
        if getattr(cat, "diferencia_dos_puntos", True) and winner_pts - loser_pts < 2:
            raise AppError(400, "PTS_DIFERENCIA", f"Set {s['numero_set']} a {req} requiere ventaja de 2 ({req}-{req-1} no, {req}-{req-2} sí)")

    # Upsert sets (don't delete history)
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
    await _avanzar_ganador(db, partido)
    return partido

async def list_partidos(db: AsyncSession, torneo_id: str = None, categoria_id: str = None, grupo_id: str = None, fase: str = None, bracket_tipo: str = None):
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
    if bracket_tipo:
        query = query.where(Partido.bracket_tipo == bracket_tipo)
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

async def crear_partido_manual(db: AsyncSession, data: dict) -> Partido:
    cat_id = data.get("categoria_id")
    res = await db.execute(select(Categoria).where(Categoria.id == cat_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no existe", {"id": cat_id})
    # validate equipos belong to same categoria
    for eid in [data.get("equipo_local_id"), data.get("equipo_visit_id")]:
        if not eid:
            raise BadRequest("EQUIPO_REQUERIDO", "Se requieren dos equipos")
        r = await db.execute(select(Equipo).where(Equipo.id == eid, Equipo.categoria_id == cat_id))
        if not r.scalar_one_or_none():
            raise BadRequest("EQUIPO_INVALIDO", f"Equipo {eid} no pertenece a la categoria")
    if data.get("equipo_local_id") == data.get("equipo_visit_id"):
        raise BadRequest("EQUIPOS_IGUALES", "Local y visita no pueden ser el mismo")
    p = Partido(
        categoria_id=cat_id,
        grupo_id=data.get("grupo_id"),
        fase=data.get("fase") or "grupos",
        llave=data.get("llave") or 0,
        equipo_local_id=data["equipo_local_id"],
        equipo_visit_id=data["equipo_visit_id"],
        cancha=data.get("cancha"),
        fecha_hora=data.get("fecha_hora"),
        bracket_tipo=data.get("bracket_tipo") or "general",
        estado="pendiente",
    )
    db.add(p)
    await db.flush()
    return p

async def actualizar_partido(db: AsyncSession, partido_id: str, data: dict, is_organizador: bool = False) -> Partido:
    res = await db.execute(select(Partido).where(Partido.id == partido_id))
    partido = res.scalar_one_or_none()
    if not partido:
        raise NotFound("PARTIDO_NOT_FOUND", "Partido no existe", {"id": partido_id})
    if partido.estado == "finalizado" and not is_organizador:
        raise AppError(400, "PARTIDO_FINALIZADO", "No se puede editar un partido finalizado - solo organizador")
    for k in ["grupo_id", "fase", "llave", "equipo_local_id", "equipo_visit_id", "cancha", "fecha_hora", "bracket_tipo"]:
        if k in data and data[k] is not None:
            setattr(partido, k, data[k])
    # validate equipos if changed
    if data.get("equipo_local_id") or data.get("equipo_visit_id"):
        cat_id = partido.categoria_id
        for eid in [partido.equipo_local_id, partido.equipo_visit_id]:
            r = await db.execute(select(Equipo).where(Equipo.id == eid, Equipo.categoria_id == cat_id))
            if not r.scalar_one_or_none():
                raise BadRequest("EQUIPO_INVALIDO", "Equipo no pertenece a la categoria")
    await db.flush()
    return partido

async def eliminar_partido(db: AsyncSession, partido_id: str, is_organizador: bool = False):
    res = await db.execute(select(Partido).where(Partido.id == partido_id))
    partido = res.scalar_one_or_none()
    if not partido:
        raise NotFound("PARTIDO_NOT_FOUND", "Partido no existe", {"id": partido_id})
    if partido.estado == "finalizado" and not is_organizador:
        raise AppError(400, "PARTIDO_FINALIZADO", "No se puede eliminar un partido finalizado - solo organizador")
    await db.delete(partido)
    await db.flush()


# ============================================================
# Marcador en vivo (bitácora de eventos del juez)
# ============================================================
INDIVIDUAL_TIPOS = {"saque_directo", "defensa", "ataque", "bloqueo"}
TIEMPOS_LIMITE = {"tiempo_muerto": 2, "tiempo_receso": 2, "tiempo_medico": None}

async def _live_partido(db: AsyncSession, partido_id: str) -> Partido:
    res = await db.execute(select(Partido).where(Partido.id == partido_id))
    partido = res.scalar_one_or_none()
    if not partido:
        raise NotFound("PARTIDO_NOT_FOUND", "Partido no existe", {"id": partido_id})
    return partido

async def _live_eventos(db: AsyncSession, partido_id: str) -> list[PartidoEvento]:
    res = await db.execute(
        select(PartidoEvento).where(PartidoEvento.partido_id == partido_id).order_by(PartidoEvento.seq)
    )
    return list(res.scalars())

def _set_target(cat: Categoria, set_num: int) -> int:
    if cat.sets_x_partido in (3, 5) and set_num == cat.sets_x_partido:
        return 15
    return cat.puntos_x_set

def _punto_numero_en_set(eventos: list[PartidoEvento], set_ganado_seq: int) -> int:
    return sum(1 for e in eventos if not e.revocado and e.tipo == "punto" and e.seq > set_ganado_seq) + 1

async def live_snapshot(db: AsyncSession, partido_id: str) -> dict:
    """Estado completo y derivado del marcador en vivo."""
    partido = await _live_partido(db, partido_id)
    res = await db.execute(select(SetPartido).where(SetPartido.partido_id == partido_id).order_by(SetPartido.numero_set))
    sets = list(res.scalars())
    res = await db.execute(select(Categoria).where(Categoria.id == partido.categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoría no encontrada")
    res_t = await db.execute(select(Rama.torneo_id).where(Rama.id == cat.rama_id))
    torneo_id = res_t.scalar_one_or_none()

    equipo_ids = [eid for eid in (partido.equipo_local_id, partido.equipo_visit_id) if eid]
    equipos: dict = {}
    atletas: dict = {}
    orden: dict = {"local": [], "visitante": []}
    if equipo_ids:
        res = await db.execute(select(Equipo).where(Equipo.id.in_(equipo_ids)))
        for eq in res.scalars():
            equipos[eq.id] = {"id": eq.id, "nombre": eq.nombre}
        res = await db.execute(select(Atleta).where(Atleta.equipo_id.in_(equipo_ids)))
        for at in res.scalars():
            atletas[at.id] = {"id": at.id, "nombre_completo": at.nombre_completo, "equipo_id": at.equipo_id}
            lado = "local" if at.equipo_id == partido.equipo_local_id else "visitante"
            orden[lado].append(at.id)

    eventos = await _live_eventos(db, partido_id)
    activos = [e for e in eventos if not e.revocado]

    # Set actual = último set archivado + 1
    current_set = (sets[-1].numero_set + 1) if sets else 1

    # Puntos en juego: eventos 'punto' posteriores al último 'set_ganado' activo
    ultimo_set_iter = 0
    for e in activos:
        if e.tipo == "set_ganado":
            ultimo_set_iter = e.seq
    score = {"local": 0, "visitante": 0}
    ultimo_punto = None
    for e in activos:
        if e.tipo == "punto" and e.seq > ultimo_set_iter:
            score[e.lado] = score.get(e.lado, 0) + 1
            ultimo_punto = e

    sets_ganados = {"local": 0, "visitante": 0}
    for s in sets:
        if s.ganador_id == partido.equipo_local_id:
            sets_ganados["local"] += 1
        elif s.ganador_id == partido.equipo_visit_id:
            sets_ganados["visitante"] += 1

    def _lado_de(atleta_id: str) -> str:
        if not atleta_id or atleta_id not in atletas:
            return ""
        eq = atletas[atleta_id]["equipo_id"]
        return "local" if eq == partido.equipo_local_id else ("visitante" if eq == partido.equipo_visit_id else "")

    # Orden de saque por dupla (último orden_saque activo por lado, si existe)
    for e in reversed(activos):
        if e.tipo == "orden_saque" and e.lado in orden:
            lista = (e.extra or {}).get("orden") or []
            if len(lista) == 2:
                orden[e.lado] = lista
                break

    # Saque actual: explícito (evento saque) o implícito (ganador del último punto)
    saque = {"lado": None, "atleta_id": None}
    ultimo_saque = None
    for e in reversed(activos):
        if e.tipo == "saque":
            ultimo_saque = e
            break
    if ultimo_punto:
        saque["lado"] = ultimo_punto.lado
        saque["atleta_id"] = orden[ultimo_punto.lado][0] if orden.get(ultimo_punto.lado) else None
    if ultimo_saque and (not ultimo_punto or _lado_de(ultimo_saque.atleta_id) == ultimo_punto.lado):
        saque["lado"] = _lado_de(ultimo_saque.atleta_id) or (ultimo_saque.lado or saque["lado"])
        saque["atleta_id"] = ultimo_saque.atleta_id
    if ultimo_saque and not ultimo_punto and not saque["atleta_id"]:
        lado_sc = _lado_de(ultimo_saque.atleta_id) or (ultimo_saque.lado or None)
        saque["lado"] = lado_sc
        saque["atleta_id"] = ultimo_saque.atleta_id if lado_sc else None

    # Tiempos y tarjetas
    tiempos = {"local": {"tiempo_muerto": 0, "tiempo_receso": 0, "tiempo_medico": 0},
               "visitante": {"tiempo_muerto": 0, "tiempo_receso": 0, "tiempo_medico": 0}}
    tarjetas = {"local": {"amarillas": 0, "rojas": 0}, "visitante": {"amarillas": 0, "rojas": 0}}
    for e in activos:
        if not e.lado or e.lado not in tiempos:
            continue
        if e.tipo in tiempos[e.lado]:
            if e.seq > ultimo_set_iter:
                tiempos[e.lado][e.tipo] += 1
        elif e.tipo == "tarjeta_amarilla":
            tarjetas[e.lado]["amarillas"] += 1
        elif e.tipo == "tarjeta_roja":
            tarjetas[e.lado]["rojas"] += 1

    # Acciones individuales por atleta
    individuales: dict = {}
    for e in activos:
        if e.tipo != "individual" or not e.atleta_id:
            continue
        ind = individuales.setdefault(e.atleta_id, {"saque_directo": 0, "defensa": 0, "ataque": 0, "bloqueo": 0})
        accion = (e.extra or {}).get("tipo", "ataque")
        if accion in ind:
            ind[accion] += 1

    # Lados invertidos (cambio de lado impar)
    n_cambios = sum(1 for e in activos if e.tipo == "cambio_lado")

    # ¿Se puede cerrar el set? (tope con/sin alargues)
    target = _set_target(cat, current_set)
    require2 = getattr(cat, "diferencia_dos_puntos", True)
    l, v = score["local"], score["visitante"]
    w = max(l, v)
    lo = min(l, v)
    can_cerrar = (w >= target and w - lo >= 2) if require2 else (w == target)

    historial = [
        {"id": e.id, "seq": e.seq, "tipo": e.tipo, "lado": e.lado, "atleta_id": e.atleta_id,
         "razon": e.razon, "numero": e.numero, "extra": e.extra,
         "creado_at": e.creado_at.isoformat() if e.creado_at else None}
        for e in activos
    ][-40:]

    return {
        "partido": {
            "id": partido.id,
            "estado": partido.estado,
            "torneo_id": torneo_id,
            "fase": partido.fase,
            "llave": partido.llave,
            "cancha": partido.cancha,
            "fecha_hora": partido.fecha_hora.isoformat() if partido.fecha_hora else None,
            "equipo_local_id": partido.equipo_local_id,
            "equipo_visit_id": partido.equipo_visit_id,
            "ganador_id": partido.ganador_id,
            "categoria": {
                "sets_x_partido": cat.sets_x_partido,
                "puntos_x_set": cat.puntos_x_set,
                "diferencia_dos_puntos": getattr(cat, "diferencia_dos_puntos", True),
            },
        },
        "equipos": equipos,
        "atletas": atletas,
        "sets": [{"numero_set": s.numero_set, "pts_local": s.pts_local, "pts_visitante": s.pts_visitante, "ganador_id": s.ganador_id} for s in sets],
        "current_set": current_set,
        "set_target": target,
        "score": score,
        "sets_ganados": sets_ganados,
        "saque": saque,
        "orden": orden,
        "tiempos": tiempos,
        "tarjetas": tarjetas,
        "individuales": individuales,
        "lados_invertidos": n_cambios % 2 == 1,
        "can_cerrar_set": can_cerrar,
        "historial": historial,
    }

async def live_evento(db: AsyncSession, partido_id: str, data) -> dict:
    """Registra una acción del juez y devuelve el snapshot actualizado."""
    partido = await _live_partido(db, partido_id)
    tipo = getattr(data, "tipo", data.get("tipo") if isinstance(data, dict) else None)
    lado = getattr(data, "lado", None) if not isinstance(data, dict) else data.get("lado")
    atleta_id = getattr(data, "atleta_id", None) if not isinstance(data, dict) else data.get("atleta_id")
    razon = getattr(data, "razon", None) if not isinstance(data, dict) else data.get("razon")
    numero = getattr(data, "numero", None) if not isinstance(data, dict) else data.get("numero")
    extra = getattr(data, "extra", None) if not isinstance(data, dict) else data.get("extra")

    if partido.estado == "finalizado" and tipo != "cambio_lado":
        raise AppError(400, "PARTIDO_FINALIZADO", "Partido finalizado - no se pueden registrar acciones")

    eventos = await _live_eventos(db, partido_id)
    seq = (eventos[-1].seq + 1) if eventos else 1

    if tipo == "inicio":
        if partido.estado == "pendiente":
            partido.estado = "en_juego"
    elif tipo == "punto":
        if lado not in ("local", "visitante"):
            raise AppError(400, "LADO_REQUERIDO", "Punto requiere lado local/visitante")
        if not partido.equipo_local_id or not partido.equipo_visit_id:
            raise AppError(400, "EQUIPOS_FALTANTES", "El partido no tiene los dos equipos")
        ultimo_set_iter = 0
        for e in eventos:
            if not e.revocado and e.tipo == "set_ganado":
                ultimo_set_iter = e.seq
        numero = _punto_numero_en_set(eventos, ultimo_set_iter)
    elif tipo == "set_ganado":
        if lado not in ("local", "visitante"):
            raise AppError(400, "LADO_REQUERIDO", "Set ganado requiere lado local/visitante")
        snap = await live_snapshot(db, partido_id)
        if not snap["can_cerrar_set"]:
            target = snap["set_target"]
            raise AppError(400, "SET_INCOMPLETO", f"El set {snap['current_set']} aún no se completa (tope {target} con ventaja de 2)")
        numero = snap["current_set"]
    elif tipo in TIEMPOS_LIMITE:
        if lado not in ("local", "visitante"):
            raise AppError(400, "LADO_REQUERIDO", f"{tipo} requiere lado local/visitante")
        limite = TIEMPOS_LIMITE[tipo]
        if limite is not None:
            snap = await live_snapshot(db, partido_id)
            usados = snap["tiempos"][lado][tipo]
            if usados >= limite:
                raise AppError(400, "LIMITE_TIEMPOS", f"{tipo}: máximo {limite} por set ({lado})")
    elif tipo in ("tarjeta_amarilla", "tarjeta_roja"):
        if lado not in ("local", "visitante"):
            raise AppError(400, "LADO_REQUERIDO", "Tarjeta requiere lado local/visitante")
        if razon and razon not in ("demora", "conducta"):
            raise AppError(400, "RAZON_INVALIDA", "razon debe ser 'demora' o 'conducta'")
    elif tipo == "saque":
        if not atleta_id:
            raise AppError(400, "ATLETA_REQUERIDO", "Saque requiere atleta_id")
        res = await db.execute(select(Atleta).where(Atleta.id == atleta_id))
        if not res.scalar_one_or_none():
            raise AppError(400, "ATLETA_INVALIDO", "Atleta no existe")
    elif tipo == "orden_saque":
        if lado not in ("local", "visitante"):
            raise AppError(400, "LADO_REQUERIDO", "orden_saque requiere lado")
        orden_lista = (extra or {}).get("orden") or []
        if len(orden_lista) != 2 or not all(orden_lista):
            raise AppError(400, "ORDEN_INVALIDO", "extra.orden debe tener 2 atleta_ids")
    elif tipo == "cambio_lado":
        pass
    elif tipo == "individual":
        if not atleta_id:
            raise AppError(400, "ATLETA_REQUERIDO", "acción individual requiere atleta_id")
        accion = (extra or {}).get("tipo", "")
        if accion not in INDIVIDUAL_TIPOS:
            raise AppError(400, "ACCION_INVALIDA", f"extra.tipo debe ser uno de {sorted(INDIVIDUAL_TIPOS)}")
    else:
        raise AppError(400, "TIPO_INVALIDO", f"Tipo de evento no soportado: {tipo}")

    evento = PartidoEvento(partido_id=partido_id, seq=seq, tipo=tipo, lado=lado, atleta_id=atleta_id, razon=razon, numero=numero, extra=extra)
    db.add(evento)
    await db.flush()

    if tipo == "set_ganado":
        snap = await live_snapshot(db, partido_id)
        set_num = snap["current_set"]
        ganador = partido.equipo_local_id if snap["score"]["local"] > snap["score"]["visitante"] else partido.equipo_visit_id
        sp = SetPartido(partido_id=partido_id, numero_set=set_num, pts_local=snap["score"]["local"], pts_visitante=snap["score"]["visitante"], ganador_id=ganador)
        db.add(sp)
        await db.flush()
        res_cat = await db.execute(select(Categoria).where(Categoria.id == partido.categoria_id))
        cat = res_cat.scalar_one_or_none()
        wins_l = snap["sets_ganados"]["local"] + (1 if ganador == partido.equipo_local_id else 0)
        wins_v = snap["sets_ganados"]["visitante"] + (1 if ganador == partido.equipo_visit_id else 0)
        if cat.sets_x_partido == 2:
            if set_num >= 2:
                pts_l = sum(s["pts_local"] for s in snap["sets"]) + snap["score"]["local"]
                pts_v = sum(s["pts_visitante"] for s in snap["sets"]) + snap["score"]["visitante"]
                if wins_l == 2 or wins_v == 2:
                    partido.ganador_id = partido.equipo_local_id if wins_l == 2 else partido.equipo_visit_id
                elif wins_l == wins_v:
                    partido.ganador_id = partido.equipo_local_id if pts_l > pts_v else (partido.equipo_visit_id if pts_v > pts_l else None)
                partido.estado = "finalizado"
        elif cat.sets_x_partido == 1:
            partido.ganador_id = ganador
            partido.estado = "finalizado"
        else:
            sets_needed = (cat.sets_x_partido // 2) + 1
            if wins_l >= sets_needed:
                partido.ganador_id = partido.equipo_local_id
                partido.estado = "finalizado"
            elif wins_v >= sets_needed:
                partido.ganador_id = partido.equipo_visit_id
                partido.estado = "finalizado"
        await db.flush()
        if partido.estado == "finalizado":
            totales_snap = await live_snapshot(db, partido_id)
            partido.tarjetas_amarillas_local = totales_snap["tarjetas"]["local"]["amarillas"]
            partido.tarjetas_rojas_local = totales_snap["tarjetas"]["local"]["rojas"]
            partido.tarjetas_amarillas_visit = totales_snap["tarjetas"]["visitante"]["amarillas"]
            partido.tarjetas_rojas_visit = totales_snap["tarjetas"]["visitante"]["rojas"]
            await db.flush()
            await _avanzar_ganador(db, partido)

    return await live_snapshot(db, partido_id)

async def live_undo(db: AsyncSession, partido_id: str) -> dict:
    """Revoca la última acción del juez (deshacer)."""
    partido = await _live_partido(db, partido_id)
    res = await db.execute(
        select(PartidoEvento).where(PartidoEvento.partido_id == partido_id, PartidoEvento.revocado == False).order_by(desc(PartidoEvento.seq))
    )
    ultimo = res.scalars().first()
    if not ultimo:
        raise AppError(400, "NADA_PARA_DESHACER", "No hay acciones para deshacer")
    ultimo.revocado = True
    if ultimo.tipo == "set_ganado":
        res2 = await db.execute(select(SetPartido).where(SetPartido.partido_id == partido_id).order_by(desc(SetPartido.numero_set)).limit(1))
        sp = res2.scalars().first()
        if sp:
            await db.delete(sp)
        if partido.estado == "finalizado":
            partido.estado = "en_juego"
            partido.ganador_id = None
    elif ultimo.tipo == "inicio":
        if partido.estado == "en_juego":
            partido.estado = "pendiente"
    await db.flush()
    return await live_snapshot(db, partido_id)
