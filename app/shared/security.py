"""
ServeTrack — JWT propio (HS256, bcrypt)
FastAPI: create_access_token, verify_token, get_current_user
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.shared.database import get_db
from app.shared.errors import Unauthorized

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

JWT_SECRET = os.getenv("JWT_SECRET") or "dev-secret-change-me-32-chars-minimum"
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM") or "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES") or "15")
JWT_REFRESH_DAYS = int(os.getenv("JWT_REFRESH_DAYS") or "7")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(data: dict) -> str:
    return create_access_token(data, expires_delta=timedelta(days=JWT_REFRESH_DAYS))

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise Unauthorized(f"Token inválido o expirado: {e}")

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    if not credentials or not credentials.credentials:
        raise Unauthorized("Falta header Authorization: Bearer <token>")
    payload = verify_token(credentials.credentials)
    user_id: str = payload.get("sub")
    if not user_id:
        raise Unauthorized("Token sin sub")
    # Lazy import to avoid circular
    from app.auth.models import User  # type: ignore
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise Unauthorized("Usuario no existe")
    # inject roles for RLS-like check
    request.state.user = user
    request.state.user_id = user_id
    request.state.roles = payload.get("roles", [])
    return user

def require_roles(*allowed: str):
    async def _checker(request: Request, user=Depends(get_current_user)):
        roles = getattr(request.state, "roles", [])
        if "super_admin" in roles:
            return user
        if not any(r in roles for r in allowed):
            from app.shared.errors import Forbidden
            raise Forbidden(f"Requiere rol: {', '.join(allowed)}")
        return user
    return _checker
