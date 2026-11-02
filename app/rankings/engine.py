"""Motor centralizado de clasificación.

Calcula las tablas de grupos y la clasificación general a partir de los
resultados reales de los partidos (partidos finalizados + sets), usando los
criterios configurados por torneo. No depende de las tablas rankings_* ni de
una prioridad fija en el código.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.equipos.models import Equipo
from app.partidos.models import Partido, SetPartido
from app.torneos.models import Categoria, Grupo, Rama, Torneo

CRITERIOS_VALIDOS = ("puntos", "sets", "puntos_partido")
CRITERIOS_DEFAULT = ["puntos", "sets", "puntos_partido"]
CRITERIOS_LABEL = {
    "puntos": "Puntos ganados",
    "sets": "Cociente de sets",
    "puntos_partido": "Cociente de puntos",
}


def normalizar_criterios(value) -> list[str]:
    """Devuelve criterios válidos, únicos y en el orden recibido."""
    if not isinstance(value, (list, tuple)):
        return list(CRITERIOS_DEFAULT)
    out = []
    for item in value:
        key = str(item).strip()
        if key in CRITERIOS_VALIDOS and key not in out:
            out.append(key)
    return out or list(CRITERIOS_DEFAULT)


def config_clasificacion(torneo: Torneo | None) -> dict:
    """Devuelve el bloque de configuración de clasificación, siempre como dict."""
    if not torneo:
        return {}
    cfg = (torneo.config_visibilidad or {}).get("clasificacion")
    return cfg if isinstance(cfg, dict) else {}


def criterios_de_torneo(torneo: Torneo | None) -> list[str]:
    if not torneo:
        return list(CRITERIOS_DEFAULT)
    return normalizar_criterios(config_clasificacion(torneo).get("criterios"))


def ratio(favor: int | None, contra: int | None) -> Fraction | float:
    """Cociente exacto. Si el divisor es cero: infinito si hay puntos/sets a favor, 0 si no."""
    f = int(favor or 0)
    c = int(contra or 0)
    if c == 0:
        return float("inf") if f > 0 else Fraction(0, 1)
    return Fraction(f, c)


def _sort_key(row: dict, criterios: Iterable[str]):
    key = []
    for criterio in criterios:
        if criterio == "puntos":
            key.append(-(row["pts"] or 0))
        elif criterio == "sets":
            key.append(-ratio(row["sets_favor"], row["sets_contra"]))
        elif criterio == "puntos_partido":
            key.append(-ratio(row["puntos_favor"], row["puntos_contra"]))
    # Desempate determinista, no deportivo: nombre y luego id.
    key.append((row.get("equipo_nombre") or "").casefold())
    key.append(str(row.get("equipo_id") or ""))
    return tuple(key)


def ordenar_stats(rows: list[dict], criterios: list[str]) -> list[dict]:
    """Ordena filas de estadísticas y les asigna posición 1..N."""
    criterios = normalizar_criterios(criterios)
    ordenadas = sorted(rows, key=lambda r: _sort_key(r, criterios))
    for pos, row in enumerate(ordenadas, start=1):
        row["posicion"] = pos
    return ordenadas


def _nueva_fila(equipo: Equipo, grupo: Grupo | None = None) -> dict:
    return {
        "equipo_id": str(equipo.id),
        "equipo_nombre": equipo.nombre,
        "grupo_id": str(equipo.grupo_id) if equipo.grupo_id else None,
        "grupo_nombre": grupo.nombre if grupo else None,
        "pj": 0, "pg": 0, "pe": 0, "pp": 0, "pts": 0,
        "sets_favor": 0, "sets_contra": 0,
        "puntos_favor": 0, "puntos_contra": 0,
        "sanciones": 0,
        "posicion": 0,
    }


def _aplicar_partido(filas: dict[str, dict], partido: Partido, sets: list[SetPartido]) -> None:
    local = filas.get(str(partido.equipo_local_id)) if partido.equipo_local_id else None
    visit = filas.get(str(partido.equipo_visit_id)) if partido.equipo_visit_id else None
    if not local or not visit:
        return

    local["pj"] += 1
    visit["pj"] += 1
    if partido.ganador_id and str(partido.ganador_id) == str(partido.equipo_local_id):
        local["pg"] += 1
        visit["pp"] += 1
    elif partido.ganador_id and str(partido.ganador_id) == str(partido.equipo_visit_id):
        visit["pg"] += 1
        local["pp"] += 1
    else:
        local["pe"] += 1
        visit["pe"] += 1

    local["sanciones"] += (partido.tarjetas_amarillas_local or 0) + (partido.tarjetas_rojas_local or 0)
    visit["sanciones"] += (partido.tarjetas_amarillas_visit or 0) + (partido.tarjetas_rojas_visit or 0)

    for s in sets:
        local["puntos_favor"] += s.pts_local
        local["puntos_contra"] += s.pts_visitante
        visit["puntos_favor"] += s.pts_visitante
        visit["puntos_contra"] += s.pts_local
        if s.ganador_id and str(s.ganador_id) == str(partido.equipo_local_id):
            local["sets_favor"] += 1
            visit["sets_contra"] += 1
        elif s.ganador_id and str(s.ganador_id) == str(partido.equipo_visit_id):
            visit["sets_favor"] += 1
            local["sets_contra"] += 1

    local["pts"] = local["pg"] * 3 + local["pe"] * 2 + local["pp"]
    visit["pts"] = visit["pg"] * 3 + visit["pe"] * 2 + visit["pp"]


async def _cargar_categoria(db: AsyncSession, categoria_id: str):
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        return None
    res = await db.execute(select(Rama).where(Rama.id == cat.rama_id))
    rama = res.scalar_one_or_none()
    torneo = None
    if rama:
        res = await db.execute(select(Torneo).where(Torneo.id == rama.torneo_id))
        torneo = res.scalar_one_or_none()
    res = await db.execute(select(Grupo).where(Grupo.categoria_id == categoria_id).order_by(Grupo.orden))
    grupos = list(res.scalars().all())
    res = await db.execute(select(Equipo).where(Equipo.categoria_id == categoria_id))
    equipos = [e for e in res.scalars().all() if e.estado not in ("eliminado", "retirada")]
    return cat, rama, torneo, grupos, equipos


async def _cargar_partidos(db: AsyncSession, categoria_id: str, solo_grupos: bool = False):
    query = select(Partido).where(Partido.categoria_id == categoria_id, Partido.estado == "finalizado")
    if solo_grupos:
        query = query.where(Partido.fase == "grupos")
    res = await db.execute(query)
    partidos = list(res.scalars().all())
    ids = [p.id for p in partidos]
    sets_por_partido: dict[str, list[SetPartido]] = {}
    if ids:
        res = await db.execute(
            select(SetPartido).where(SetPartido.partido_id.in_(ids)).order_by(SetPartido.partido_id, SetPartido.numero_set)
        )
        for s in res.scalars().all():
            sets_por_partido.setdefault(str(s.partido_id), []).append(s)
    return partidos, sets_por_partido


async def compute_group_rankings(db: AsyncSession, categoria_id: str, grupo_id: str | None = None) -> list[dict]:
    cargado = await _cargar_categoria(db, categoria_id)
    if not cargado:
        return []
    _, _, torneo, grupos, equipos = cargado
    criterios = criterios_de_torneo(torneo)
    grupos_por_id = {str(g.id): g for g in grupos}
    seleccionados = [g for g in grupos if grupo_id is None or str(g.id) == str(grupo_id)]
    partidos, sets_por_partido = await _cargar_partidos(db, categoria_id, solo_grupos=True)

    salida: list[dict] = []
    for grupo in seleccionados:
        filas = {
            str(e.id): _nueva_fila(e, grupos_por_id.get(str(e.grupo_id)))
            for e in equipos if str(e.grupo_id) == str(grupo.id)
        }
        for p in partidos:
            if str(p.grupo_id) != str(grupo.id):
                continue
            _aplicar_partido(filas, p, sets_por_partido.get(str(p.id), []))
        rows = ordenar_stats(list(filas.values()), criterios)
        salida.extend(rows)
    return salida


async def compute_general_rankings(db: AsyncSession, categoria_id: str) -> list[dict]:
    cargado = await _cargar_categoria(db, categoria_id)
    if not cargado:
        return []
    _, _, torneo, grupos, equipos = cargado
    criterios = criterios_de_torneo(torneo)
    grupos_por_id = {str(g.id): g for g in grupos}
    filas = {str(e.id): _nueva_fila(e, grupos_por_id.get(str(e.grupo_id))) for e in equipos}
    partidos, sets_por_partido = await _cargar_partidos(db, categoria_id, solo_grupos=False)
    for p in partidos:
        _aplicar_partido(filas, p, sets_por_partido.get(str(p.id), []))
    return ordenar_stats(list(filas.values()), criterios)


async def compute_group_ranking(db: AsyncSession, grupo_id: str) -> list[dict]:
    res = await db.execute(select(Grupo).where(Grupo.id == grupo_id))
    grupo = res.scalar_one_or_none()
    if not grupo:
        return []
    return await compute_group_rankings(db, str(grupo.categoria_id), grupo_id)


async def compute_tournament_rankings(db: AsyncSession, torneo_id: str) -> list[dict]:
    res = await db.execute(
        select(Categoria).join(Rama, Categoria.rama_id == Rama.id).where(Rama.torneo_id == torneo_id).order_by(Categoria.nombre)
    )
    categorias = list(res.scalars().all())
    out: list[dict] = []
    for cat in categorias:
        rows = await compute_general_rankings(db, str(cat.id))
        for row in rows:
            row["categoria_id"] = str(cat.id)
            row["categoria_nombre"] = cat.nombre
        out.extend(rows)
    return out


def criterios_label(criterios: list[str]) -> str:
    return " > ".join(CRITERIOS_LABEL.get(c, c) for c in normalizar_criterios(criterios))
