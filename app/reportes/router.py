from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.database import get_db
from app.shared.security import get_current_user
from app.reportes.service import report_fixture, report_posiciones, report_bracket

router = APIRouter(prefix="/reportes/{torneo_id}", tags=["reportes"])

@router.get("/fixture", response_model=dict)
async def fixture(torneo_id: str, categoria_id: str = None, db: AsyncSession = Depends(get_db)):
    cache = await report_fixture(db, torneo_id, categoria_id)
    return {"success": True, "data": {"tipo": "fixture", "pdf_url": cache.pdf_url, "generated_at": cache.generated_at.isoformat() if cache.generated_at else None, "expira_at": cache.expira_at.isoformat() if cache.expira_at else None}, "error": None}

@router.get("/posiciones", response_model=dict)
async def posiciones(torneo_id: str, db: AsyncSession = Depends(get_db)):
    cache = await report_posiciones(db, torneo_id)
    return {"success": True, "data": {"tipo": "posiciones", "pdf_url": cache.pdf_url}, "error": None}

@router.get("/bracket", response_model=dict)
async def bracket(torneo_id: str, categoria_id: str = None, db: AsyncSession = Depends(get_db)):
    if not categoria_id:
        from app.shared.errors import AppError
        raise AppError(400, "CATEGORIA_REQUERIDA", "categoria_id requerido para bracket")
    cache = await report_bracket(db, torneo_id, categoria_id)
    return {"success": True, "data": {"tipo": "bracket", "pdf_url": cache.pdf_url}, "error": None}

@router.get("/stats-equipo/{equipo_id}", response_model=dict)
async def stats_equipo(torneo_id: str, equipo_id: str, db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": {"torneo_id": torneo_id, "equipo_id": equipo_id, "pdf_url": f"supabase://reportes/{torneo_id}/stats_{equipo_id}.pdf"}, "error": None}

@router.get("/ranking-general", response_model=dict)
async def ranking_general(torneo_id: str, categoria_id: str = None, db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": {"torneo_id": torneo_id, "categoria_id": categoria_id, "pdf_url": f"supabase://reportes/{torneo_id}/ranking.pdf"}, "error": None}
