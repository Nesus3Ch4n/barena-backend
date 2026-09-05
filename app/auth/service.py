"""
ServeTrack — Auth Service (screaming: auth/service)
Lógica de dominio: registro, login, refresh, reclamo
Sin sobreingeniería: funciones puras + AsyncSession
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from sqlalchemy.exc import IntegrityError

from app.auth.models import User, Profile, Role, user_roles
from app.shared.security import hash_password, verify_password, create_access_token, create_refresh_token, verify_token
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

# ---------- Register ----------
async def register_user(db: AsyncSession, email: str, password: str, nombre_completo: str) -> tuple[User, str, str]:
    email = email.lower().strip()
    existing = await get_user_by_email(db, email)
    if existing:
        raise AppError(409, "EMAIL_EXISTS", "Email ya registrado", {"email": email})

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    await db.flush()  # to get id

    profile = Profile(id=user.id, nombre_completo=nombre_completo)
    db.add(profile)

    # rol por defecto: atleta
    await db.execute(insert(user_roles).values(user_id=user.id, role_id="atleta"))

    await db.flush()
    roles = ["atleta"]
    access = create_access_token({"sub": user.id, "roles": roles, "email": user.email})
    refresh = create_refresh_token({"sub": user.id, "type": "refresh"})
    return user, access, refresh

# ---------- Login ----------
async def login_user(db: AsyncSession, email: str, password: str) -> tuple[User, str, str]:
    user = await get_user_by_email(db, email.lower())
    if not user or not verify_password(password, user.password_hash):
        raise Unauthorized("Email o contraseña incorrectos")
    roles = await get_roles_for_user(db, user.id)
    if not roles:
        roles = ["atleta"]
    access = create_access_token({"sub": user.id, "roles": roles, "email": user.email})
    refresh = create_refresh_token({"sub": user.id, "type": "refresh"})
    return user, access, refresh

# ---------- Refresh ----------
async def refresh_token(db: AsyncSession, refresh_token_str: str) -> tuple[str, str]:
    payload = verify_token(refresh_token_str)
    if payload.get("type") != "refresh":
        raise Unauthorized("Token no es de tipo refresh")
    user_id = payload.get("sub")
    if not user_id:
        raise Unauthorized("Refresh sin sub")
    # verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise Unauthorized("Usuario no existe")
    roles = await get_roles_for_user(db, user.id)
    new_access = create_access_token({"sub": user.id, "roles": roles, "email": user.email})
    new_refresh = create_refresh_token({"sub": user.id, "type": "refresh"})
    return new_access, new_refresh

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
    # Verificar que user no tenga ya atleta con ese codigo? Se permite múltiples equipos
    # Actualizar atleta.user_id = user_id
    await db.execute(text("UPDATE atletas SET user_id = :uid WHERE id = :aid"), {"uid": user_id, "aid": str(row["id"])})
    await db.flush()
    return {"atleta_id": str(row["id"]), "equipo_id": str(row["equipo_id"]), "nombre": row["nombre_completo"]}


