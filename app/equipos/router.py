from uuid import UUID
from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.shared.database import get_db
from app.shared.security import get_current_user, require_roles
from app.shared.errors import AppError, NotFound, Forbidden
from app.equipos.schemas import EquipoCreate, EquipoAprobarIn
from app.equipos.service import create_equipo, list_equipos, aprobar_equipo, rechazar_equipo, get_equipo_atletas, verify_torneo_owner
import csv, io

router = APIRouter(prefix="/torneos/{torneo_id}/equipos", tags=["equipos"])
equipo_router = APIRouter(prefix="/equipos", tags=["equipos"])

@router.post("", status_code=201, response_model=dict)
async def crear_equipo(torneo_id: str, body: EquipoCreate, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    is_super = "super_admin" in getattr(request.state, "roles", [])
    equipo = await create_equipo(db, torneo_id, body, user.id, is_super)
    return {"success": True, "data": {"id": equipo.id, "nombre": equipo.nombre, "estado": equipo.estado, "categoria_id": equipo.categoria_id}, "error": None}

@router.get("", response_model=dict)
async def listar_equipos(torneo_id: str, categoria_id: str = None, grupo_id: str = None, estado: str = None, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    equipos = await list_equipos(db, torneo_id, categoria_id, grupo_id, estado)
    data = [{"id": e.id, "nombre": e.nombre, "categoria_id": e.categoria_id, "grupo_id": e.grupo_id, "estado": e.estado, "seed": e.seed} for e in equipos]
    return {"success": True, "data": data, "error": None}

@router.post("/bulk", response_model=dict)
async def bulk_equipos(torneo_id: str, request: Request, background: BackgroundTasks, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    is_super = "super_admin" in getattr(request.state, "roles", [])
    body = await request.json()
    if not isinstance(body, list):
        raise AppError(400, "BULK_INVALID", "Body debe ser lista de equipos")
    if len(body) > 50:
        raise AppError(400, "BULK_LIMIT", "Máximo 50 equipos por bulk")
    await verify_torneo_owner(db, torneo_id, user.id, is_super)
    creados = []
    for item in body:
        from app.equipos.schemas import EquipoCreate
        eq_data = EquipoCreate(**item)
        eq = await create_equipo(db, torneo_id, eq_data, user.id, is_super)
        creados.append(eq.id)
    await db.commit()
    return {"success": True, "data": {"creados": len(creados), "ids": creados}, "error": None}

@equipo_router.patch("/{equipo_id}/aprobar", response_model=dict)
async def aprobar(equipo_id: str, body: EquipoAprobarIn, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    is_super = "super_admin" in getattr(request.state, "roles", [])
    # Verify owner BEFORE mutation
    from app.equipos.models import Equipo as EqModel
    from app.torneos.models import Categoria, Rama
    res = await db.execute(select(EqModel).where(EqModel.id == equipo_id))
    eq_check = res.scalar_one_or_none()
    if eq_check:
        res2 = await db.execute(select(Rama.torneo_id).join(Categoria, Categoria.rama_id == Rama.id).where(Categoria.id == eq_check.categoria_id))
        tid = res2.scalar_one_or_none()
        if tid:
            await verify_torneo_owner(db, str(tid), user.id, is_super)
    equipo = await aprobar_equipo(db, equipo_id, body.grupo_id, body.seed, None, user.id, is_super)
    return {"success": True, "data": {"id": equipo.id, "estado": equipo.estado, "grupo_id": equipo.grupo_id, "seed": equipo.seed}, "error": None}

@equipo_router.patch("/{equipo_id}/rechazar", response_model=dict)
async def rechazar(equipo_id: str, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    is_super = "super_admin" in getattr(request.state, "roles", [])
    # Verify owner BEFORE mutation
    from app.equipos.models import Equipo
    from app.torneos.models import Categoria, Rama
    res = await db.execute(select(Equipo).where(Equipo.id == equipo_id))
    equipo_check = res.scalar_one_or_none()
    if not equipo_check:
        raise NotFound("EQUIPO_NOT_FOUND", "Equipo no existe", {"id": equipo_id})
    res2 = await db.execute(select(Rama.torneo_id).join(Categoria, Categoria.rama_id == Rama.id).where(Categoria.id == equipo_check.categoria_id))
    tid = res2.scalar_one_or_none()
    if tid:
        await verify_torneo_owner(db, str(tid), user.id, is_super)
    equipo = await rechazar_equipo(db, equipo_id)
    return {"success": True, "data": {"id": equipo.id, "estado": equipo.estado}, "error": None}

@equipo_router.get("/{equipo_id}/atletas", response_model=dict)
async def atletas_equipo(equipo_id: str, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    is_super = "super_admin" in getattr(request.state, "roles", [])
    atletas = await get_equipo_atletas(db, equipo_id)
    data = []
    for a in atletas:
        item = {"id": a.id, "nombre_completo": a.nombre_completo, "posicion": a.posicion}
        if is_super or (a.user_id and str(a.user_id) == str(user.id)):
            item["codigo_reclamo"] = a.codigo_reclamo
        data.append(item)
    return {"success": True, "data": data, "error": None}
