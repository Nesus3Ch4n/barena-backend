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
