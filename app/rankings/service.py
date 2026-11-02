from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


async def global_ranking(db: AsyncSession, limit: int = 50):
    """Ranking global del circuito: suma pts de rankings_general por dupla de atletas.

    Los puntos de clasificación (pts) no dependen del orden de criterios; solo
    las posiciones. Por eso este ranking de circuito puede seguir usando la
    caché rankings_general, que los triggers mantienen al registrar resultados.
    """
    from app.rankings.models import RankingGeneral
    from app.torneos.models import Rama, Categoria, Torneo
    from app.equipos.models import Equipo
    from app.atletas.models import Atleta

    rows = (await db.execute(
        select(RankingGeneral.equipo_id, RankingGeneral.pts, Rama.torneo_id, Equipo.nombre, Equipo.ciudad)
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
    for equipo_id, pts, torneo_id, equipo_nombre, ciudad in rows:
        jugadores = tuple(sorted(nombres.get(equipo_id) or []))
        clave = ("dupla", jugadores) if jugadores else ("equipo", equipo_id)
        item = acumulado.setdefault(clave, {
            "equipo_id": equipo_id,
            "nombre": " / ".join(jugadores) or equipo_nombre,
            "ciudad": ciudad,
            "pts": 0,
            "torneos": set(),
        })
        item["pts"] += pts or 0
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
