from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.database import get_db
from app.shared.security import get_current_user, require_roles
from app.atletas.service import list_atletas_equipo, get_atleta, get_atleta_por_codigo, mis_duplas, buscar_atletas

router = APIRouter(prefix="/atletas", tags=["atletas"])

@router.get("/mios", response_model=dict)
async def mias(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": await mis_duplas(db, user.id), "error": None}

@router.get("/buscar", response_model=dict)
async def buscar(q: str = "", user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not q.strip() or len(q.strip()) < 2:
        return {"success": True, "data": [], "error": None}
    return {"success": True, "data": await buscar_atletas(db, q), "error": None}

@router.get("/por-codigo/{codigo}", response_model=dict)
async def por_codigo(codigo: str, user=Depends(require_roles("organizador", "super_admin")), db: AsyncSession = Depends(get_db)):
    return {"success": True, "data": await get_atleta_por_codigo(db, codigo), "error": None}

def _validate_uuid(value: str):
    from uuid import UUID as _UUID
    from app.shared.errors import BadRequest
    try:
        _UUID(value)
    except ValueError:
        raise BadRequest("INVALID_UUID", "ID inválido")

@router.get("/{atleta_id}", response_model=dict)
async def detalle(atleta_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _validate_uuid(atleta_id)
    atleta = await get_atleta(db, atleta_id)
    return {"success": True, "data": {"id": atleta.id, "nombre_completo": atleta.nombre_completo, "posicion": atleta.posicion, "equipo_id": atleta.equipo_id, "codigo_reclamo": atleta.codigo_reclamo}, "error": None}

@router.get("/equipo/{equipo_id}", response_model=dict)
async def por_equipo(equipo_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    atletas = await list_atletas_equipo(db, equipo_id)
    return {"success": True, "data": [{"id": a.id, "nombre_completo": a.nombre_completo, "posicion": a.posicion} for a in atletas], "error": None}
