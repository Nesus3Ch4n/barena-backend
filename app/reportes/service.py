import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.reportes.models import ReporteCache
from app.torneos.models import Torneo
from app.shared.errors import NotFound

async def get_or_create_cache(db: AsyncSession, torneo_id: str, tipo: str, params: dict, generator):
    res = await db.execute(select(ReporteCache).where(ReporteCache.torneo_id == torneo_id, ReporteCache.tipo == tipo).order_by(ReporteCache.generated_at.desc()))
    cache = res.scalars().first()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    # Compare params as sorted JSON strings to avoid dict key order issues
    params_str = json.dumps(params, sort_keys=True, default=str)
    cache_params_str = json.dumps(cache.params, sort_keys=True, default=str) if cache and cache.params else None
    if cache and cache.expira_at and cache.expira_at > now and params_str == cache_params_str:
        return cache
    pdf_url = await generator()
    new = ReporteCache(torneo_id=torneo_id, tipo=tipo, params=params, pdf_url=pdf_url)
    db.add(new)
    await db.flush()
    return new

async def report_fixture(db: AsyncSession, torneo_id: str, categoria_id: str = None):
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    if not res.scalar_one_or_none():
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    async def gen():
        return f"supabase://reportes/{torneo_id}/fixture_{categoria_id or 'all'}.pdf"
    cache = await get_or_create_cache(db, torneo_id, "fixture", {"categoria_id": categoria_id}, gen)
    return cache

async def report_posiciones(db: AsyncSession, torneo_id: str):
    return await report_fixture(db, torneo_id, None)

async def report_bracket(db: AsyncSession, torneo_id: str, categoria_id: str):
    return await report_fixture(db, torneo_id, categoria_id)
