from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, insert, update
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field

from app.shared.database import get_db
from app.shared.security import get_current_user
from app.shared.errors import Forbidden, NotFound
from app.auth.models import User, Profile, user_roles
from app.auth.service import get_roles_for_user

router = APIRouter(prefix="/admin/perfiles", tags=["admin-perfiles"])

async def require_super_admin(user, db):
    roles = await get_roles_for_user(db, user.id)
    if "super_admin" not in roles:
        raise Forbidden("Solo super_admin puede gestionar perfiles")
    return roles

class PerfilUpdateIn(BaseModel):
    nombre_completo: Optional[str] = Field(None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = Field(None, max_length=500)
    telefono: Optional[str] = Field(None, max_length=20)
    doc_identidad: Optional[str] = Field(None, max_length=30)

class RolesAssignIn(BaseModel):
    roles: List[str] = Field(min_length=1)

@router.get("", response_model=dict)
async def listar_perfiles(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_super_admin(user, db)
    # join users + profiles
    res = await db.execute(select(User, Profile).outerjoin(Profile, Profile.id == User.id).order_by(User.created_at.desc()))
    rows = res.all()
    data = []
    for u, p in rows:
        roles = await get_roles_for_user(db, u.id)
        data.append({
            "id": u.id,
            "email": u.email,
            "nombre_completo": p.nombre_completo if p else None,
            "roles": roles,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "avatar_url": p.avatar_url if p else None,
            "telefono": p.telefono if p else None,
            "doc_identidad": p.doc_identidad if p else None,
        })
    return {"success": True, "data": data, "error": None}

@router.get("/{perfil_id}", response_model=dict)
async def detalle_perfil(perfil_id: str, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_super_admin(user, db)
    res = await db.execute(select(User).where(User.id == perfil_id))
    u = res.scalar_one_or_none()
    if not u:
        raise NotFound("USER_NOT_FOUND", "Usuario no existe", {"id": perfil_id})
    res2 = await db.execute(select(Profile).where(Profile.id == perfil_id))
    p = res2.scalar_one_or_none()
    roles = await get_roles_for_user(db, perfil_id)
    return {"success": True, "data": {
        "id": u.id,
        "email": u.email,
        "nombre_completo": p.nombre_completo if p else None,
        "roles": roles,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "avatar_url": p.avatar_url if p else None,
        "telefono": p.telefono if p else None,
        "doc_identidad": p.doc_identidad if p else None,
    }, "error": None}

@router.patch("/{perfil_id}", response_model=dict)
async def actualizar_perfil(perfil_id: str, body: PerfilUpdateIn, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_super_admin(user, db)
    res = await db.execute(select(User).where(User.id == perfil_id))
    u = res.scalar_one_or_none()
    if not u:
        raise NotFound("USER_NOT_FOUND", "Usuario no existe", {"id": perfil_id})
    # update email if provided and different
    if body.email and body.email.lower() != u.email.lower():
        # check duplicate
        res2 = await db.execute(select(User).where(User.email == body.email.lower()))
        if res2.scalar_one_or_none():
            from app.shared.errors import AppError
            raise AppError(409, "EMAIL_EXISTS", "Email ya existe", {"email": body.email})
        u.email = body.email.lower()
    # update profile
    res3 = await db.execute(select(Profile).where(Profile.id == perfil_id))
    p = res3.scalar_one_or_none()
    if not p:
        # create if missing
        p = Profile(id=perfil_id, nombre_completo=body.nombre_completo or "Sin nombre")
        db.add(p)
        await db.flush()
    if body.nombre_completo is not None:
        p.nombre_completo = body.nombre_completo.strip()
    if body.avatar_url is not None:
        p.avatar_url = body.avatar_url
    if body.telefono is not None:
        p.telefono = body.telefono
    if body.doc_identidad is not None:
        p.doc_identidad = body.doc_identidad
    await db.flush()
    roles = await get_roles_for_user(db, perfil_id)
    return {"success": True, "data": {"id": u.id, "email": u.email, "nombre_completo": p.nombre_completo, "roles": roles}, "error": None}

@router.delete("/{perfil_id}", response_model=dict)
async def eliminar_perfil(perfil_id: str, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_super_admin(user, db)
    if str(user.id) == perfil_id:
        from app.shared.errors import AppError
        raise AppError(400, "CANNOT_DELETE_SELF", "No puedes eliminarte a ti mismo")
    res = await db.execute(select(User).where(User.id == perfil_id))
    u = res.scalar_one_or_none()
    if not u:
        raise NotFound("USER_NOT_FOUND", "Usuario no existe", {"id": perfil_id})
    # check if user is organizador with torneos? allow delete anyway, cascade will handle
    await db.execute(delete(user_roles).where(user_roles.c.user_id == perfil_id))
    await db.delete(u)
    await db.flush()
    return {"success": True, "data": {"deleted": True}, "error": None}

@router.post("/{perfil_id}/roles", response_model=dict)
async def asignar_roles(perfil_id: str, body: RolesAssignIn, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_super_admin(user, db)
    res = await db.execute(select(User).where(User.id == perfil_id))
    if not res.scalar_one_or_none():
        raise NotFound("USER_NOT_FOUND", "Usuario no existe", {"id": perfil_id})
    # validate roles
    valid = {"super_admin","organizador","juez_anotador","atleta"}
    for r in body.roles:
        if r not in valid:
            from app.shared.errors import AppError
            raise AppError(400, "ROL_INVALIDO", f"Rol no válido: {r}", {"valid": list(valid)})
    # replace roles
    await db.execute(delete(user_roles).where(user_roles.c.user_id == perfil_id))
    for r in set(body.roles):
        await db.execute(insert(user_roles).values(user_id=perfil_id, role_id=r))
    await db.flush()
    roles = await get_roles_for_user(db, perfil_id)
    return {"success": True, "data": {"roles": roles}, "error": None}
