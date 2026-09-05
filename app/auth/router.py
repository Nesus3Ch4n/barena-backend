from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/health")
async def health():
    return {"success": True, "data": {"status": "auth ok"}}

# TODO: POST /register, /login, /refresh, /me, /reclamar (Fase auth completa)
