from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.database import get_db
from app.shared.security import get_current_user
from app.partidos.schemas import GenerarFixtureIn, ProgramarIn, ResultadoIn
from app.partidos.service import generar_fixture, programar_partido, registrar_resultado, list_partidos, get_partido

router = APIRouter(prefix="/partidos", tags=["partidos"])
torneo_partidos_router = APIRouter(prefix="/torneos/{torneo_id}/partidos", tags=["partidos"])
categoria_fixture_router = APIRouter(prefix="/categorias/{categoria_id}", tags=["partidos"])

@categoria_fixture_router.post("/generar-fixture", response_model=dict)
async def generar(categoria_id: str, body: GenerarFixtureIn = None, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    partidos = await generar_fixture(db, categoria_id)
    return {"success": True, "data": {"generados": len(partidos), "partidos": [{"id": p.id, "grupo_id": p.grupo_id, "local": p.equipo_local_id, "visit": p.equipo_visit_id} for p in partidos]}, "error": None}

@torneo_partidos_router.get("", response_model=dict)
async def listar(torneo_id: str, categoria_id: str = None, grupo_id: str = None, fase: str = None, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    partidos = await list_partidos(db, torneo_id, categoria_id, grupo_id, fase)
    data = [{"id": p.id, "categoria_id": p.categoria_id, "grupo_id": p.grupo_id, "fase": p.fase, "local": p.equipo_local_id, "visit": p.equipo_visit_id, "cancha": p.cancha, "fecha_hora": p.fecha_hora.isoformat() if p.fecha_hora else None, "estado": p.estado, "ganador_id": p.ganador_id} for p in partidos]
    return {"success": True, "data": data, "error": None}

@router.patch("/{partido_id}/programar", response_model=dict)
async def programar(partido_id: str, body: ProgramarIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    partido = await programar_partido(db, partido_id, body.cancha, body.fecha_hora)
    return {"success": True, "data": {"id": partido.id, "cancha": partido.cancha, "fecha_hora": partido.fecha_hora.isoformat() if partido.fecha_hora else None}, "error": None}

@router.post("/{partido_id}/resultado", response_model=dict)
async def resultado(partido_id: str, body: ResultadoIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    sets = [{"numero_set": s.numero_set, "pts_local": s.pts_local, "pts_visitante": s.pts_visitante, "duracion_min": s.duracion_min} for s in body.sets]
    partido = await registrar_resultado(db, partido_id, sets)
    return {"success": True, "data": {"id": partido.id, "estado": partido.estado, "ganador_id": partido.ganador_id}, "error": None}

@router.get("/{partido_id}", response_model=dict)
async def detalle(partido_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    partido, sets = await get_partido(db, partido_id)
    return {"success": True, "data": {"partido": {"id": partido.id, "estado": partido.estado, "ganador_id": partido.ganador_id, "local": partido.equipo_local_id, "visit": partido.equipo_visit_id, "cancha": partido.cancha}, "sets": [{"numero_set": s.numero_set, "pts_local": s.pts_local, "pts_visitante": s.pts_visitante, "ganador_id": s.ganador_id} for s in sets]}, "error": None}

@router.get("/{partido_id}/qr", response_model=dict)
async def qr(partido_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # retorna URL para juez, en MVP es mismo id
    return {"success": True, "data": {"qr_url": f"/juez/partido/{partido_id}", "partido_id": partido_id}, "error": None}
