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
    """Ranking global del circuito: agrega pts de rankings_general (finalizados) de todos los torneos públicos, por equipo."""
    from sqlalchemy import func
    from app.torneos.models import Rama, Categoria, Torneo
    from app.equipos.models import Equipo
    # pts agregados por equipo (suma de rankings_general en torneos públicos con categorías activas e inscritos aprobados)
    query = (
        select(
            Equipo.id,
            Equipo.nombre,
            Equipo.ciudad,
            func.sum(RankingGeneral.pts).label("pts"),
            func.count(RankingGeneral.id).label("torneos"),
        )
        .join(Categoria, RankingGeneral.categoria_id == Categoria.id)
        .join(Rama, Categoria.rama_id == Rama.id)
        .join(Torneo, Rama.torneo_id == Torneo.id)
        .join(Equipo, Equipo.id == RankingGeneral.equipo_id)
        .where(Torneo.publico == True, Equipo.estado == "aprobado")
        .group_by(Equipo.id, Equipo.nombre, Equipo.ciudad)
        .order_by(func.sum(RankingGeneral.pts).desc())
        .limit(limit)
    )
    res = await db.execute(query)
    rows = res.all()
    result = []
    for pos, (equipo_id, nombre, ciudad, pts, torneos) in enumerate(rows, start=1):
        result.append({
            "posicion": pos,
            "equipo_id": str(equipo_id),
            "nombre": nombre,
            "ciudad": ciudad,
            "pts": pts or 0,
            "torneos": torneos,
        })
    return result
