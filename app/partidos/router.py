from uuid import UUID
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.shared.database import get_db
from app.shared.security import get_current_user, require_roles
from app.shared.errors import AppError, NotFound, Forbidden
from app.partidos.schemas import GenerarFixtureIn, PartidoCreate, PartidoUpdate, ProgramarIn, ResultadoIn
from app.partidos.service import crear_partido_manual, actualizar_partido, eliminar_partido, generar_fixture, programar_partido, registrar_resultado, list_partidos, get_partido

router = APIRouter(prefix="/partidos", tags=["partidos"])
torneo_partidos_router = APIRouter(prefix="/torneos/{torneo_id}/partidos", tags=["partidos"])
categoria_fixture_router = APIRouter(prefix="/categorias/{categoria_id}", tags=["partidos"])

async def _verify_categoria_owner(db: AsyncSession, categoria_id: str, user_id: str, is_super: bool):
    if is_super:
        return
    from app.torneos.models import Categoria, Rama, Torneo
    res = await db.execute(select(Categoria).where(Categoria.id == categoria_id))
    cat = res.scalar_one_or_none()
    if not cat:
        raise NotFound("CATEGORIA_NOT_FOUND", "Categoria no existe")
    res2 = await db.execute(select(Rama.torneo_id).where(Rama.id == cat.rama_id))
    torneo_id = res2.scalar_one_or_none()
    if not torneo_id:
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no encontrado")
    res3 = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    torneo = res3.scalar_one_or_none()
    if torneo and torneo.organizador_id != user_id:
        raise Forbidden("No eres organizador de este torneo")

@categoria_fixture_router.get("/grupos", response_model=dict)
async def listar_grupos_categoria(categoria_id: str, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []))
    from app.torneos.models import Grupo
    res = await db.execute(select(Grupo).where(Grupo.categoria_id == categoria_id).order_by(Grupo.orden))
    grupos = res.scalars().all()
    return {"success": True, "data": [{"id": g.id, "nombre": g.nombre, "orden": g.orden} for g in grupos], "error": None}

@categoria_fixture_router.post("/generar-fixture", response_model=dict)
async def generar(categoria_id: str, body: GenerarFixtureIn = None, request: Request = None, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []))
    partidos = await generar_fixture(db, categoria_id, body.bracket_tipo if body else None)
    return {"success": True, "data": {"generados": len(partidos), "partidos": [{"id": p.id, "grupo_id": p.grupo_id, "local": p.equipo_local_id, "visit": p.equipo_visit_id, "bracket_tipo": p.bracket_tipo} for p in partidos]}, "error": None}

@categoria_fixture_router.post("/avanzar-bracket", response_model=dict)
async def avanzar_bracket(categoria_id: str, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []))
    partidos = await generar_bracket_desde_ranking(db, categoria_id)
    return {"success": True, "data": {"generados": len(partidos), "partidos": [{"id": p.id, "fase": p.fase, "local": p.equipo_local_id, "visit": p.equipo_visit_id, "bracket_tipo": p.bracket_tipo} for p in partidos]}, "error": None}

@torneo_partidos_router.get("", response_model=dict)
async def listar(torneo_id: str, categoria_id: str = None, grupo_id: str = None, fase: str = None, bracket_tipo: str = None, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    partidos = await list_partidos(db, torneo_id, categoria_id, grupo_id, fase, bracket_tipo)
    data = [{"id": p.id, "categoria_id": p.categoria_id, "grupo_id": p.grupo_id, "fase": p.fase, "local": p.equipo_local_id, "visit": p.equipo_visit_id, "cancha": p.cancha, "fecha_hora": p.fecha_hora.isoformat() if p.fecha_hora else None, "estado": p.estado, "ganador_id": p.ganador_id, "bracket_tipo": p.bracket_tipo} for p in partidos]
    return {"success": True, "data": data, "error": None}

@router.patch("/{partido_id}/programar", response_model=dict)
async def programar(partido_id: str, body: ProgramarIn, request: Request, user=Depends(require_roles("organizador", "juez_anotador", "super_admin")), db: AsyncSession = Depends(get_db)):
    is_org = "organizador" in getattr(request.state, "roles", []) or "super_admin" in getattr(request.state, "roles", [])
    partido = await programar_partido(db, partido_id, body.cancha, body.fecha_hora, is_organizador=is_org)
    return {"success": True, "data": {"id": partido.id, "cancha": partido.cancha, "fecha_hora": partido.fecha_hora.isoformat() if partido.fecha_hora else None}, "error": None}

@router.post("/{partido_id}/resultado", response_model=dict)
async def resultado(partido_id: str, body: ResultadoIn, request: Request, user=Depends(require_roles("juez_anotador", "organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    sets = [{"numero_set": s.numero_set, "pts_local": s.pts_local, "pts_visitante": s.pts_visitante, "duracion_min": s.duracion_min} for s in body.sets]
    is_org = "organizador" in getattr(request.state, "roles", []) or "super_admin" in getattr(request.state, "roles", [])
    partido = await registrar_resultado(db, partido_id, sets, is_organizador=is_org)
    return {"success": True, "data": {"id": partido.id, "estado": partido.estado, "ganador_id": partido.ganador_id}, "error": None}

@router.get("/{partido_id}", response_model=dict)
async def detalle(partido_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    partido, sets = await get_partido(db, partido_id)
    return {"success": True, "data": {"partido": {"id": partido.id, "estado": partido.estado, "ganador_id": partido.ganador_id, "local": partido.equipo_local_id, "visit": partido.equipo_visit_id, "cancha": partido.cancha}, "sets": [{"numero_set": s.numero_set, "pts_local": s.pts_local, "pts_visitante": s.pts_visitante, "ganador_id": s.ganador_id} for s in sets]}, "error": None}

@router.get("/{partido_id}/qr", response_model=dict)
async def qr(partido_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": {"qr_url": f"/juez/partido/{partido_id}", "partido_id": partido_id}, "error": None}

@router.patch("/{partido_id}", response_model=dict)
async def actualizar(partido_id: str, body: PartidoUpdate, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, (await db.execute(select(Partido.categoria_id).where(Partido.id == partido_id))).scalar_one_or_none() or "", user.id, "super_admin" in getattr(request.state, "roles", []))
    is_org = "organizador" in getattr(request.state, "roles", []) or "super_admin" in getattr(request.state, "roles", [])
    partido = await actualizar_partido(db, partido_id, body.model_dump(exclude_unset=True), is_organizador=is_org)
    return {"success": True, "data": {"id": partido.id, "grupo_id": partido.grupo_id, "fase": partido.fase, "bracket_tipo": partido.bracket_tipo}, "error": None}

@router.delete("/{partido_id}", response_model=dict)
async def eliminar(partido_id: str, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    # verify owner via partido -> categoria
    res = await db.execute(select(Partido.categoria_id).where(Partido.id == partido_id))
    cat_id = res.scalar_one_or_none()
    if cat_id:
        await _verify_categoria_owner(db, cat_id, user.id, "super_admin" in getattr(request.state, "roles", []))
    is_org = "organizador" in getattr(request.state, "roles", []) or "super_admin" in getattr(request.state, "roles", [])
    await eliminar_partido(db, partido_id, is_organizador=is_org)
    return {"success": True, "data": {"deleted": True}, "error": None}

@categoria_fixture_router.post("/partidos", status_code=201, response_model=dict)
async def crear_manual(categoria_id: str, body: PartidoCreate, request: Request, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    await _verify_categoria_owner(db, categoria_id, user.id, "super_admin" in getattr(request.state, "roles", []))
    partido = await crear_partido_manual(db, body.model_dump())
    return {"success": True, "data": {"id": partido.id, "local": partido.equipo_local_id, "visit": partido.equipo_visit_id}, "error": None}
