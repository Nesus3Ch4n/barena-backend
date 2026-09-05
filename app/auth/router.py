from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.shared.database import get_db
from app.shared.security import get_current_user
from app.auth.schemas import RegisterIn, LoginIn, TokenOut, MeOut, ReclamarIn
from app.auth.service import register_user, login_user, refresh_token, reclamar_atleta, get_roles_for_user, get_profile
from app.auth.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/health")
async def health():
    return {"success": True, "data": {"status": "auth ok"}, "error": None}

@router.post("/register", response_model=dict, status_code=201)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await register_user(db, body.email, body.password, body.nombre_completo)
    # commit handled by get_db, but flush already done
    return {"success": True, "data": {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "user_id": user.id}, "error": None}

@router.post("/login", response_model=dict)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await login_user(db, body.email, body.password)
    return {"success": True, "data": {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "user_id": user.id}, "error": None}

@router.post("/refresh", response_model=dict)
async def refresh(body: dict, db: AsyncSession = Depends(get_db)):
    token = body.get("refresh_token")
    if not token:
        from app.shared.errors import AppError
        raise AppError(400, "MISSING_REFRESH", "Falta refresh_token")
    new_access, new_refresh = await refresh_token(db, token)
    return {"success": True, "data": {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}, "error": None}

@router.get("/me", response_model=dict)
async def me(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    roles = await get_roles_for_user(db, user.id)
    profile = await get_profile(db, user.id)
    return {
        "success": True,
        "data": {
            "id": user.id,
            "email": user.email,
            "nombre_completo": profile.nombre_completo if profile else None,
            "roles": roles,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "error": None,
    }

@router.post("/reclamar", response_model=dict)
async def reclamar(body: ReclamarIn, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await reclamar_atleta(db, user.id, body.codigo)
    return {"success": True, "data": result, "error": None}
