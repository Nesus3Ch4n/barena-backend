from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.database import get_db
from app.shared.security import get_current_user
from app.rankings.service import list_rankings_grupo, list_rankings_categoria_grupo, list_rankings_general, list_rankings_torneo

router = APIRouter(prefix="/rankings", tags=["rankings"])
categoria_router = APIRouter(prefix="/categorias/{categoria_id}/rankings", tags=["rankings"])
torneo_router = APIRouter(prefix="/torneos/{torneo_id}/rankings", tags=["rankings"])

@router.get("/grupo/{grupo_id}", response_model=dict)
async def grupo(grupo_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = await list_rankings_grupo(db, grupo_id)
    return {"success": True, "data": [{"equipo_id": r.equipo_id, "pj": r.pj, "pg": r.pg, "pp": r.pp, "sets_favor": r.sets_favor, "sets_contra": r.sets_contra, "puntos_favor": r.puntos_favor, "puntos_contra": r.puntos_contra, "posicion": r.posicion} for r in data], "error": None}

@categoria_router.get("/grupo", response_model=dict)
async def categoria_grupo(categoria_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = await list_rankings_categoria_grupo(db, categoria_id)
    return {"success": True, "data": [{"grupo_id": r.grupo_id, "equipo_id": r.equipo_id, "posicion": r.posicion, "pg": r.pg} for r in data], "error": None}

@categoria_router.get("/general", response_model=dict)
async def general(categoria_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = await list_rankings_general(db, categoria_id)
    return {"success": True, "data": [{"equipo_id": r.equipo_id, "pj": r.pj, "pg": r.pg, "posicion": r.posicion} for r in data], "error": None}

@torneo_router.get("", response_model=dict)
async def torneo_rankings(torneo_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = await list_rankings_torneo(db, torneo_id)
    return {"success": True, "data": [{"categoria_id": r.categoria_id, "equipo_id": r.equipo_id, "posicion": r.posicion} for r in data], "error": None}
