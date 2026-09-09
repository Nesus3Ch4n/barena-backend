from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.database import get_db
from app.shared.security import get_current_user
from app.config.service import get_flags, set_flag

router = APIRouter(prefix="/config", tags=["config"])

@router.get("/health")
async def health(): return {"success": True, "data": {"status": "config ok"}, "error": None}

@router.get("/flags", response_model=dict)
async def flags(db: AsyncSession = Depends(get_db)):
    data = await get_flags(db)
    return {"success": True, "data": data, "error": None}

@router.get("/torneo/{torneo_id}", response_model=dict)
async def torneo_config(torneo_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # retorna config_visibilidad
    from sqlalchemy import select
    from app.torneos.models import Torneo
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res.scalar_one_or_none()
    if not torneo:
        from app.shared.errors import NotFound
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    return {"success": True, "data": {"torneo_id": torneo.id, "config_visibilidad": torneo.config_visibilidad, "publico": torneo.publico}, "error": None}

@router.get("/deportes")
async def listar_deportes(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from app.torneos.models import Deporte
    res = await db.execute(select(Deporte).where(Deporte.activo == True))
    deportes = [{"id": d.id, "nombre": d.nombre, "icono": d.icono} for d in res.scalars().all()]
    return {"success": True, "data": deportes, "error": None}

@router.patch("/flags/{clave}", response_model=dict)
async def update_flag(clave: str, body: dict, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # solo super_admin
    roles = getattr(user, "_roles", None)  # fallback via request.state checked in security, but here check via DB
    # will rely on require_roles wrapper; simplified check
    from app.auth.service import get_roles_for_user
    roles = await get_roles_for_user(db, user.id)
    if "super_admin" not in roles:
        from app.shared.errors import Forbidden
        raise Forbidden("Solo super_admin")
    row = await set_flag(db, clave, body.get("valor", body))
    return {"success": True, "data": {"clave": row.clave, "valor": row.valor}, "error": None}
