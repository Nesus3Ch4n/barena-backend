from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.database import get_db
from app.rankings.service import list_rankings_grupo, list_rankings_categoria_grupo, list_rankings_general, list_rankings_torneo, global_ranking
from app.equipos.models import Equipo
from app.torneos.models import Grupo

router = APIRouter(prefix="/rankings", tags=["rankings"])
categoria_router = APIRouter(prefix="/categorias/{categoria_id}/rankings", tags=["rankings"])
torneo_router = APIRouter(prefix="/torneos/{torneo_id}/rankings", tags=["rankings"])
global_router = APIRouter(prefix="/public/rankings", tags=["rankings"])


async def _equipo_nombres(db: AsyncSession, ids: list):
    ids = [i for i in ids if i]
    if not ids:
        return {}
    res = await db.execute(select(Equipo).where(Equipo.id.in_(ids)))
    return {r.id: r.nombre for r in res.scalars()}


def _grupo_full(r):
    return {
        "equipo_id": r.equipo_id,
        "pj": r.pj, "pg": r.pg, "pe": r.pe, "pp": r.pp,
        "pts": r.pts,
        "sets_favor": r.sets_favor, "sets_contra": r.sets_contra,
        "puntos_favor": r.puntos_favor, "puntos_contra": r.puntos_contra,
        "sanciones": r.sanciones, "posicion": r.posicion,
    }


def _general_full(r):
    return {
        "equipo_id": r.equipo_id,
        "pj": r.pj, "pg": r.pg, "pe": r.pe, "pp": r.pp,
        "pts": r.pts,
        "sets_favor": getattr(r, "sets_favor", 0) or 0,
        "sets_contra": getattr(r, "sets_contra", 0) or 0,
        "puntos_favor": getattr(r, "puntos_favor", 0) or 0,
        "puntos_contra": getattr(r, "puntos_contra", 0) or 0,
        "sanciones": r.sanciones, "posicion": r.posicion,
    }


@router.get("/grupo/{grupo_id}", response_model=dict)
async def grupo(grupo_id: str, db: AsyncSession = Depends(get_db)):
    data = await list_rankings_grupo(db, grupo_id)
    nombres = await _equipo_nombres(db, [r.equipo_id for r in data])
    return {"success": True, "data": [{**_grupo_full(r), "equipo_nombre": nombres.get(r.equipo_id, "Equipo")} for r in data], "error": None}


@categoria_router.get("/grupo", response_model=dict)
async def categoria_grupo(categoria_id: str, db: AsyncSession = Depends(get_db)):
    data = await list_rankings_categoria_grupo(db, categoria_id)
    nombres = await _equipo_nombres(db, [r.equipo_id for r in data])
    res = await db.execute(select(Grupo).where(Grupo.categoria_id == categoria_id))
    gnames = {g.id: g.nombre for g in res.scalars()}
    return {"success": True, "data": [{**_grupo_full(r), "grupo_id": r.grupo_id, "grupo_nombre": gnames.get(r.grupo_id, r.grupo_id), "equipo_nombre": nombres.get(r.equipo_id, "Equipo")} for r in data], "error": None}


@categoria_router.get("/general", response_model=dict)
async def general(categoria_id: str, db: AsyncSession = Depends(get_db)):
    data = await list_rankings_general(db, categoria_id)
    nombres = await _equipo_nombres(db, [r.equipo_id for r in data])
    return {"success": True, "data": [{**_general_full(r), "equipo_nombre": nombres.get(r.equipo_id, "Equipo")} for r in data], "error": None}


@torneo_router.get("", response_model=dict)
async def torneo_rankings(torneo_id: str, db: AsyncSession = Depends(get_db)):
    data = await list_rankings_torneo(db, torneo_id)
    nombres = await _equipo_nombres(db, [r.equipo_id for r in data])
    return {"success": True, "data": [{"categoria_id": r.categoria_id, "equipo_id": r.equipo_id, "equipo_nombre": nombres.get(r.equipo_id, "Equipo"), "posicion": r.posicion} for r in data], "error": None}


@global_router.get("", response_model=dict)
async def global_public_ranking(db: AsyncSession = Depends(get_db)):
    data = await global_ranking(db)
    return {"success": True, "data": data, "error": None}