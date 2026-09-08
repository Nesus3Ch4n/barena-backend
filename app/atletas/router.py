from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.database import get_db
from app.shared.security import get_current_user
from app.atletas.service import list_atletas_equipo, get_atleta

router = APIRouter(prefix="/atletas", tags=["atletas"])

@router.get("/{atleta_id}", response_model=dict)
async def detalle(atleta_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    atleta = await get_atleta(db, atleta_id)
    return {"success": True, "data": {"id": atleta.id, "nombre_completo": atleta.nombre_completo, "posicion": atleta.posicion, "equipo_id": atleta.equipo_id, "codigo_reclamo": atleta.codigo_reclamo}, "error": None}

@router.get("/equipo/{equipo_id}", response_model=dict)
async def por_equipo(equipo_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    atletas = await list_atletas_equipo(db, equipo_id)
    return {"success": True, "data": [{"id": a.id, "nombre_completo": a.nombre_completo, "posicion": a.posicion} for a in atletas], "error": None}
