"""TEMPORAL mig017: tabla pqr + indice.
ELIMINAR este archivo tras aplicar en produccion.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.shared.security import get_current_user

router = APIRouter(prefix="/tmp", tags=["tmp"])


@router.post("/pqr017", response_model=dict)
async def pqr017(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    roles = getattr(request.state, "roles", [])
    if "organizador" not in roles and "super_admin" not in roles:
        from app.shared.errors import Forbidden
        raise Forbidden("temporal: solo organizador")
    await db.execute(text("""
CREATE TABLE IF NOT EXISTS pqr (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    torneo_id UUID NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    tipo VARCHAR(20) NOT NULL DEFAULT 'peticion',
    asunto VARCHAR(120) NOT NULL,
    mensaje TEXT NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'abierta',
    respuesta TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
)"""))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_pqr_torneo ON pqr (torneo_id)"))
    tab = (await db.execute(text(
        "SELECT tablename FROM pg_tables WHERE tablename='pqr'"
    ))).scalar_one_or_none()
    await db.commit()
    return {"success": True, "data": {"tabla": tab}, "error": None}
