from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.rankings.models import RankingGrupo, RankingGeneral
from app.shared.errors import NotFound

async def list_rankings_grupo(db: AsyncSession, grupo_id: str):
    res = await db.execute(select(RankingGrupo).where(RankingGrupo.grupo_id == grupo_id).order_by(RankingGrupo.posicion))
    return res.scalars().all()

async def list_rankings_categoria_grupo(db: AsyncSession, categoria_id: str):
    # necesita join grupos
    from app.torneos.models import Grupo
    res = await db.execute(select(RankingGrupo).join(Grupo, RankingGrupo.grupo_id == Grupo.id).where(Grupo.categoria_id == categoria_id).order_by(Grupo.nombre, RankingGrupo.posicion))
    return res.scalars().all()

async def list_rankings_general(db: AsyncSession, categoria_id: str):
    res = await db.execute(select(RankingGeneral).where(RankingGeneral.categoria_id == categoria_id).order_by(RankingGeneral.posicion))
    rows = res.scalars().all()
    if not rows:
        return []
    return rows

async def list_rankings_torneo(db: AsyncSession, torneo_id: str):
    from app.torneos.models import Rama, Categoria, Grupo
    # todos los rankings del torneo
    res = await db.execute(select(RankingGeneral).join(Categoria, RankingGeneral.categoria_id == Categoria.id).join(Rama, Categoria.rama_id == Rama.id).where(Rama.torneo_id == torneo_id))
    return res.scalars().all()

async def global_ranking(db: AsyncSession, limit: int = 50):
    """Ranking global del circuito: suma pts de rankings_general por dupla de atletas."""
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
