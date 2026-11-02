from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.shared.security import get_optional_user
from app.shared.errors import NotFound
from app.rankings.engine import (
    compute_group_ranking,
    compute_group_rankings,
    compute_general_rankings,
    compute_tournament_rankings,
)
from app.rankings.service import global_ranking
from app.torneos.models import Grupo, Rama, Categoria, Torneo
from app.torneos.service import requiere_visibilidad

router = APIRouter(prefix="/rankings", tags=["rankings"])
categoria_router = APIRouter(prefix="/categorias/{categoria_id}/rankings", tags=["rankings"])
torneo_router = APIRouter(prefix="/torneos/{torneo_id}/rankings", tags=["rankings"])
global_router = APIRouter(prefix="/public/rankings", tags=["rankings"])


async def _torneo_de_categoria(db: AsyncSession, categoria_id: str):
    res = await db.execute(select(Rama.torneo_id).join(Categoria, Categoria.rama_id == Rama.id).where(Categoria.id == categoria_id))
    return res.scalar_one_or_none()


async def _torneo_de_grupo(db: AsyncSession, grupo_id: str):
    res = await db.execute(
        select(Rama.torneo_id)
        .join(Categoria, Categoria.rama_id == Rama.id)
        .join(Grupo, Grupo.categoria_id == Categoria.id)
        .where(Grupo.id == grupo_id)
    )
    return res.scalar_one_or_none()


async def _exigir_posiciones(db: AsyncSession, torneo_id, user) -> None:
    if user is not None or not torneo_id:
        return
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res.scalar_one_or_none()
    if not torneo or not torneo.publico:
        raise NotFound("TORNEO_NOT_PUBLIC", "Torneo no es público o no existe", {"id": str(torneo_id)})
    requiere_visibilidad(torneo, "posiciones_visible", "ranking_visible")


@router.get("/grupo/{grupo_id}", response_model=dict)
async def grupo(grupo_id: str, user=Depends(get_optional_user), db: AsyncSession = Depends(get_db)):
    torneo_id = await _torneo_de_grupo(db, grupo_id)
    await _exigir_posiciones(db, torneo_id, user)
    data = await compute_group_ranking(db, grupo_id)
    return {"success": True, "data": data, "error": None}


@categoria_router.get("/grupo", response_model=dict)
async def categoria_grupo(categoria_id: str, user=Depends(get_optional_user), db: AsyncSession = Depends(get_db)):
    await _exigir_posiciones(db, await _torneo_de_categoria(db, categoria_id), user)
    data = await compute_group_rankings(db, categoria_id)
    return {"success": True, "data": data, "error": None}


@categoria_router.get("/general", response_model=dict)
async def general(categoria_id: str, user=Depends(get_optional_user), db: AsyncSession = Depends(get_db)):
    torneo_id = await _torneo_de_categoria(db, categoria_id)
    await _exigir_posiciones(db, torneo_id, user)
    data = await compute_general_rankings(db, categoria_id)
    return {"success": True, "data": data, "error": None}


@torneo_router.get("", response_model=dict)
async def torneo_rankings(torneo_id: str, user=Depends(get_optional_user), db: AsyncSession = Depends(get_db)):
    await _exigir_posiciones(db, torneo_id, user)
    data = await compute_tournament_rankings(db, torneo_id)
    return {"success": True, "data": data, "error": None}


@global_router.get("", response_model=dict)
async def global_public_ranking(db: AsyncSession = Depends(get_db)):
    data = await global_ranking(db)
    return {"success": True, "data": data, "error": None}
