from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.database import get_db
from app.shared.security import get_current_user, require_roles
from app.estadisticas.schemas import EstadisticaIn
from app.estadisticas.service import upsert_estadistica, list_estadisticas, get_atleta_stats

router = APIRouter(prefix="/partidos/{partido_id}/estadisticas", tags=["estadisticas"])
atleta_router = APIRouter(prefix="/atletas", tags=["estadisticas"])

@router.post("", response_model=dict)
async def upsert(partido_id: str, body: EstadisticaIn, user=Depends(require_roles("juez_anotador", "organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    est = await upsert_estadistica(db, partido_id, body)
    return {"success": True, "data": {"id": est.id, "atleta_id": est.atleta_id, "puntos_total": est.ataques_pts + est.bloqueos_pts + est.saques_directos}, "error": None}

@router.get("", response_model=dict)
async def listar(partido_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stats = await list_estadisticas(db, partido_id)
    data = [{"id": s.id, "atleta_id": s.atleta_id, "ataques_pts": s.ataques_pts, "bloqueos_pts": s.bloqueos_pts, "saques_directos": s.saques_directos, "puntos_total": s.ataques_pts + s.bloqueos_pts + s.saques_directos} for s in stats]
    return {"success": True, "data": data, "error": None}

@atleta_router.get("/{atleta_id}/stats", response_model=dict)
async def stats_atleta(atleta_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = await get_atleta_stats(db, atleta_id)
    return {"success": True, "data": data, "error": None}
