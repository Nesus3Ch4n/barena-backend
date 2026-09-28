"""TEMPORAL mig017: columna rol en torneo_jueces + indice unico por rol.
ELIMINAR este archivo tras aplicar en produccion.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.shared.security import get_current_user
from app.admin.router import require_super_admin

router = APIRouter(prefix="/tmp", tags=["tmp"])


@router.post("/mig017", response_model=dict)
async def mig017(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_super_admin(user, db)
    await db.execute(text("ALTER TABLE torneo_jueces ADD COLUMN IF NOT EXISTS rol VARCHAR(24)"))
    await db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_torneo_jueces_rol "
        "ON torneo_jueces (torneo_id, rol) WHERE rol IS NOT NULL"
    ))
    col = (await db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='torneo_jueces' AND column_name='rol'"
    ))).scalar_one_or_none()
    idx = (await db.execute(text(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename='torneo_jueces' AND indexname='uq_torneo_jueces_rol'"
    ))).scalar_one_or_none()
    n = (await db.execute(text("SELECT COUNT(*) FROM torneo_jueces"))).scalar_one_or_none()
    await db.commit()
    return {"success": True, "data": {"col": col, "idx": idx, "filas": n}, "error": None}
