from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config.models import ConfigGlobal

async def get_flags(db: AsyncSession):
    res = await db.execute(select(ConfigGlobal))
    rows = res.scalars().all()
    flags = {r.clave: r.valor for r in rows}
    # defaults
    flags.setdefault("freemium", True)
    flags.setdefault("realtime_enabled", True)
    return flags

async def set_flag(db: AsyncSession, clave: str, valor: dict):
    res = await db.execute(select(ConfigGlobal).where(ConfigGlobal.clave == clave))
    row = res.scalar_one_or_none()
    if row:
        row.valor = valor
    else:
        row = ConfigGlobal(clave=clave, valor=valor)
        db.add(row)
    await db.flush()
    return row
