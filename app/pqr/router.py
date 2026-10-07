from uuid import UUID as _UUID
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional
from app.shared.database import get_db
from app.shared.security import get_current_user
from app.shared.errors import BadRequest
from app.pqr.service import radicar_pqr, listar_pqr, responder_pqr, borrar_pqr

router = APIRouter(tags=["pqr"])


def _validate_uuid(value: str, field: str = "id"):
    try:
        _UUID(value)
    except ValueError:
        raise BadRequest("INVALID_UUID", f"{field} inválido")


class PQRRadicarIn(BaseModel):
    tipo: str = Field(default="peticion", pattern="^(peticion|queja|reclamo|sugerencia|felicitacion)$")
    asunto: str = Field(min_length=2, max_length=120)
    mensaje: str = Field(min_length=2, max_length=2000)


class PQRResponderIn(BaseModel):
    estado: Optional[str] = Field(default=None, pattern="^(abierta|en_proceso|cerrada)$")
    respuesta: Optional[str] = Field(default=None, max_length=2000)


@router.post("/torneos/{torneo_id}/pqr", response_model=dict)
async def radicar(torneo_id: str, body: PQRRadicarIn, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _validate_uuid(torneo_id, "torneo_id")
    data = await radicar_pqr(db, torneo_id, user.id, body.tipo, body.asunto, body.mensaje)
    return {"success": True, "data": data, "error": None}


@router.get("/torneos/{torneo_id}/pqr", response_model=dict)
async def listar(torneo_id: str, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _validate_uuid(torneo_id, "torneo_id")
    is_super = "super_admin" in getattr(request.state, "roles", [])
    is_org = "organizador" in getattr(request.state, "roles", [])
    return {"success": True, "data": await listar_pqr(db, torneo_id, user.id, is_super, is_org), "error": None}


@router.patch("/pqr/{pqr_id}", response_model=dict)
async def responder(pqr_id: str, body: PQRResponderIn, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _validate_uuid(pqr_id, "pqr_id")
    is_super = "super_admin" in getattr(request.state, "roles", [])
    is_org = "organizador" in getattr(request.state, "roles", [])
    return {"success": True, "data": await responder_pqr(db, pqr_id, user.id, is_super, is_org, body.estado, body.respuesta), "error": None}


@router.delete("/pqr/{pqr_id}", response_model=dict)
async def borrar(pqr_id: str, request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _validate_uuid(pqr_id, "pqr_id")
    is_super = "super_admin" in getattr(request.state, "roles", [])
    is_org = "organizador" in getattr(request.state, "roles", [])
    return {"success": True, "data": await borrar_pqr(db, pqr_id, user.id, is_super, is_org), "error": None}
