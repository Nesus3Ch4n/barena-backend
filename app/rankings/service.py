from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


async def global_ranking(db: AsyncSession, limit: int = 50):
    """Ranking global del circuito: suma los puntos de clasificación por dupla.

    Usa pg/pe/pp de la caché rankings_general (actualizada por los triggers de
    resultados) y aplica los puntos por resultado configurados en cada torneo.
    """
    from app.rankings.models import RankingGeneral
    from app.rankings.engine import normalizar_puntos
    from app.torneos.models import Rama, Categoria, Torneo
    from app.equipos.models import Equipo
    from app.atletas.models import Atleta

    rows = (await db.execute(
        select(
            RankingGeneral.equipo_id,
            RankingGeneral.pg,
            RankingGeneral.pe,
            RankingGeneral.pp,
            Rama.torneo_id,
            Equipo.nombre,
            Equipo.ciudad,
            Torneo.config_visibilidad,
        )
        .join(Categoria, RankingGeneral.categoria_id == Categoria.id)
        .join(Rama, Categoria.rama_id == Rama.id)
        .join(Torneo, Rama.torneo_id == Torneo.id)
        .join(Equipo, Equipo.id == RankingGeneral.equipo_id)
        .where(Torneo.publico == True, Equipo.estado == "aprobado")
    )).all()
    if not rows:
        return []

    equipo_ids = {r[0] for r in rows}
    atletas = (await db.execute(
        select(Atleta.equipo_id, Atleta.nombre_completo).where(Atleta.equipo_id.in_(equipo_ids))
    )).all()
    nombres: dict = {}
    for eq_id, nombre in atletas:
        nombres.setdefault(eq_id, []).append(nombre)

    acumulado: dict = {}
    for equipo_id, pg, pe, pp, torneo_id, equipo_nombre, ciudad, config_visibilidad in rows:
        config = config_visibilidad if isinstance(config_visibilidad, dict) else {}
        clasificacion = config.get("clasificacion") if isinstance(config.get("clasificacion"), dict) else {}
        puntos = normalizar_puntos(clasificacion.get("puntos"))
        pts = (pg or 0) * puntos["ganado"] + (pe or 0) * puntos["empatado"] + (pp or 0) * puntos["perdido"]
        jugadores = tuple(sorted(nombres.get(equipo_id) or []))
        clave = ("dupla", jugadores) if jugadores else ("equipo", equipo_id)
        item = acumulado.setdefault(clave, {
            "equipo_id": equipo_id,
            "nombre": " / ".join(jugadores) or equipo_nombre,
            "ciudad": ciudad,
            "pts": 0,
            "torneos": set(),
        })
        item["pts"] += pts
        item["torneos"].add(torneo_id)

    ordenados = sorted(acumulado.values(), key=lambda x: (-x["pts"], x["nombre"]))
    return [{
        "posicion": pos,
        "equipo_id": str(x["equipo_id"]),
        "nombre": x["nombre"],
        "ciudad": x["ciudad"],
        "pts": x["pts"],
        "torneos": len(x["torneos"]),
    } for pos, x in enumerate(ordenados[:limit], start=1)]
