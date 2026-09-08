from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.shared.database import get_db
from app.shared.security import get_current_user
from app.shared.errors import AppError, NotFound, Forbidden
from app.torneos.schemas import TorneoCreate, VisibilidadUpdate
from app.torneos.service import create_torneo, get_torneo_detail, list_torneos, update_visibilidad, get_public_by_slug
from app.torneos.models import Torneo

router = APIRouter(prefix="/torneos", tags=["torneos"])
public_router = APIRouter(prefix="/public", tags=["public"])

@router.post("", status_code=201, response_model=dict)
async def crear_torneo(body: TorneoCreate, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await create_torneo(db, user.id, body)
    torneo = result["torneo"]
    return {"success": True, "data": {"id": torneo.id, "slug": torneo.slug, "nombre": torneo.nombre, "organizador_id": torneo.organizador_id}, "error": None}

@router.get("", response_model=dict)
async def listar_torneos(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    is_super = "super_admin" in getattr(request.state, "roles", [])
    torneos = await list_torneos(db, user.id, is_super)
    data = [{"id": t.id, "nombre": t.nombre, "slug": t.slug, "estado": t.estado, "publico": t.publico, "ciudad": t.ciudad} for t in torneos]
    return {"success": True, "data": data, "error": None}

@router.get("/{torneo_id}", response_model=dict)
async def detalle_torneo(torneo_id: str, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # check ownership via RLS-like logic
    is_super = "super_admin" in getattr(request.state, "roles", [])
    # fetch
    result = await get_torneo_detail(db, torneo_id)
    torneo = result["torneo"]
    if torneo.organizador_id != user.id and not is_super:
        # allow if public? detail should be allowed for public even if not owner
        if not torneo.publico:
            raise Forbidden("No tienes permiso para ver este torneo")
    ramas_data = []
    for rama, cats in result["ramas"]:
        ramas_data.append({"id": rama.id, "tipo": rama.tipo, "nombre_custom": rama.nombre_custom, "categorias": [{"id": c.id, "nombre": c.nombre, "formato": c.formato, "equipos_x_grupo": c.equipos_x_grupo, "avance_x_grupo": c.avance_x_grupo} for c in cats]})
    return {"success": True, "data": {"torneo": {"id": torneo.id, "nombre": torneo.nombre, "slug": torneo.slug, "deporte_id": torneo.deporte_id, "organizador_id": torneo.organizador_id, "fecha_inicio": str(torneo.fecha_inicio) if torneo.fecha_inicio else None, "fecha_fin": str(torneo.fecha_fin) if torneo.fecha_fin else None, "sede": torneo.sede, "ciudad": torneo.ciudad, "estado": torneo.estado, "publico": torneo.publico, "config_visibilidad": torneo.config_visibilidad}, "ramas": ramas_data}, "error": None}

@router.patch("/{torneo_id}/visibilidad", response_model=dict)
async def patch_visibilidad(torneo_id: str, body: VisibilidadUpdate, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    is_super = "super_admin" in getattr(request.state, "roles", [])
    # verify owner
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    if torneo.organizador_id != user.id and not is_super:
        raise Forbidden("No eres organizador de este torneo")
    updated = await update_visibilidad(db, torneo_id, body)
    return {"success": True, "data": {"id": updated.id, "config_visibilidad": updated.config_visibilidad, "publico": updated.publico}, "error": None}

@router.patch("/{torneo_id}/publicar-fixture", response_model=dict)
async def publicar_fixture(torneo_id: str, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # shortcut to set fixture_visible true
    return await patch_visibilidad(torneo_id, VisibilidadUpdate(fixture_visible=True), request, user, db)

@public_router.get("/torneo/{slug}", response_model=dict)
async def public_torneo(slug: str, db: AsyncSession = Depends(get_db)):
    torneo = await get_public_by_slug(db, slug)
    # also fetch ramas for public
    result = await get_torneo_detail(db, torneo.id)
    ramas_data = [{"id": r.id, "tipo": r.tipo, "categorias": [{"id": c.id, "nombre": c.nombre, "formato": c.formato} for c in cats]} for r, cats in result["ramas"]]
    return {"success": True, "data": {"torneo": {"id": torneo.id, "nombre": torneo.nombre, "slug": torneo.slug, "sede": torneo.sede, "ciudad": torneo.ciudad, "fecha_inicio": str(torneo.fecha_inicio) if torneo.fecha_inicio else None}, "ramas": ramas_data}, "error": None}
