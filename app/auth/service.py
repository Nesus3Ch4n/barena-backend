"""
ServeTrack — Auth Service (screaming: auth/service)
Lógica de dominio: registro, login, refresh con rotación jti, reclamo
"""
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete, update
from sqlalchemy.exc import IntegrityError

from app.auth.models import User, Profile, Role, user_roles, RefreshToken
from app.shared.security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    verify_token, JWT_REFRESH_DAYS
)
from app.shared.errors import AppError, Unauthorized

# ---------- Helpers ----------
async def get_roles_for_user(db: AsyncSession, user_id: str) -> list[str]:
    result = await db.execute(select(user_roles.c.role_id).where(user_roles.c.user_id == user_id))
    return [row[0] for row in result.all()]

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()

async def get_profile(db: AsyncSession, user_id: str):
    result = await db.execute(select(Profile).where(Profile.id == user_id))
    return result.scalar_one_or_none()

async def _store_refresh_token(db: AsyncSession, user_id: str, token_str: str) -> None:
    payload = verify_token(token_str)
    jti = payload.get("jti")
    if not jti:
        return
    now = datetime.now(timezone.utc)
    expira = now + timedelta(days=JWT_REFRESH_DAYS)
    await db.execute(insert(RefreshToken).values(user_id=user_id, jti=jti, expira_at=expira))

# ---------- Register ----------
async def register_user(db: AsyncSession, email: str, password: str, nombre_completo: str) -> tuple[User, str, str]:
    email = email.lower().strip()
    existing = await get_user_by_email(db, email)
    if existing:
        raise AppError(409, "EMAIL_EXISTS", "Email ya registrado", {"email": email})

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    await db.flush()

    profile = Profile(id=user.id, nombre_completo=nombre_completo)
    db.add(profile)

    await db.execute(insert(user_roles).values(user_id=user.id, role_id="atleta"))
    await db.flush()

    roles = ["atleta"]
    access = create_access_token({"sub": str(user.id), "roles": roles, "email": user.email})
    refresh = create_refresh_token({"sub": str(user.id)})
    await _store_refresh_token(db, user.id, refresh)
    return user, access, refresh

# ---------- Login ----------
async def login_user(db: AsyncSession, email: str, password: str) -> tuple[User, str, str]:
    user = await get_user_by_email(db, email.lower())
    if not user or not verify_password(password, user.password_hash):
        raise Unauthorized("Email o contraseña incorrectos")
    roles = await get_roles_for_user(db, user.id)
    if not roles:
        roles = ["atleta"]
    access = create_access_token({"sub": str(user.id), "roles": roles, "email": user.email})
    refresh = create_refresh_token({"sub": str(user.id)})
    await _store_refresh_token(db, user.id, refresh)
    return user, access, refresh

# ---------- Refresh (rotación con jti) ----------
async def refresh_token(db: AsyncSession, refresh_token_str: str) -> tuple[str, str]:
    payload = verify_token(refresh_token_str)
    if payload.get("type") != "refresh":
        raise Unauthorized("Token no es de tipo refresh")
    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        raise Unauthorized("Refresh sin sub o jti")

    # verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise Unauthorized("Usuario no existe")

    # verify jti not revoked
    res = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    row = res.scalar_one_or_none()
    if not row or row.revoked:
        raise Unauthorized("Refresh token inválido o ya usado")
    if row.user_id != user_id:
        raise Unauthorized("Refresh token no pertenece a este usuario")

    # revoke old token
    row.revoked = True
    await db.flush()

    # issue new pair
    roles = await get_roles_for_user(db, user.id)
    new_access = create_access_token({"sub": str(user.id), "roles": roles, "email": user.email})
    new_refresh = create_refresh_token({"sub": str(user.id)})
    await _store_refresh_token(db, user.id, new_refresh)
    return new_access, new_refresh

# ---------- Logout ----------
async def logout_user(db: AsyncSession, refresh_token_str: str) -> bool:
    payload = verify_token(refresh_token_str)
    jti = payload.get("jti")
    if not jti:
        return False
    await db.execute(update(RefreshToken).where(RefreshToken.jti == jti).values(revoked=True))
    await db.flush()
    return True

# ---------- Reclamar atleta ----------
async def reclamar_atleta(db: AsyncSession, user_id: str, codigo: str) -> dict:
    codigo = codigo.upper().strip()
    from sqlalchemy import text
    res = await db.execute(text("SELECT id, equipo_id, nombre_completo, user_id FROM atletas WHERE codigo_reclamo = :cod"), {"cod": codigo})
    row = res.mappings().first()
    if not row:
        raise AppError(404, "CODIGO_NOT_FOUND", "Código de reclamo no existe", {"codigo": codigo})
    if row["user_id"] is not None:
        raise AppError(409, "CODIGO_ALREADY_CLAIMED", "Código ya reclamado", {"codigo": codigo})
    await db.execute(text("UPDATE atletas SET user_id = :uid WHERE id = :aid"), {"uid": user_id, "aid": str(row["id"])})
    await db.flush()
    return {"atleta_id": str(row["id"]), "equipo_id": str(row["equipo_id"]), "nombre": row["nombre_completo"]}
