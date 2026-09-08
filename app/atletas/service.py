from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.atletas.models import Atleta
from app.torneos.models import Grupo
from app.shared.errors import NotFound

async def list_atletas_equipo(db: AsyncSession, equipo_id: str):
    res = await db.execute(select(Atleta).where(Atleta.equipo_id == equipo_id))
    return res.scalars().all()

async def get_atleta(db: AsyncSession, atleta_id: str):
    res = await db.execute(select(Atleta).where(Atleta.id == atleta_id))
    atleta = res.scalar_one_or_none()
    if not atleta:
        raise NotFound("ATLETA_NOT_FOUND", "Atleta no existe", {"id": atleta_id})
    return atleta
