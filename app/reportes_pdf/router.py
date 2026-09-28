from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional
from app.shared.database import get_db
from app.shared.security import get_current_user
from app.reportes_pdf.service import generar_reporte

router = APIRouter(prefix="/reportes", tags=["reportes-pdf"])


class ReporteIn(BaseModel):
    torneo_id: Optional[str] = None
    categoria_id: Optional[str] = None
    partido_id: Optional[str] = None
    atleta_id: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/{tipo}", response_model=None)
async def crear_reporte(tipo: str, body: ReporteIn, request: Request,
                        user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if tipo not in ("perfil_atleta", "perfil_juez", "parcial", "final", "partido"):
        from app.shared.errors import AppError
        raise AppError(400, "TIPO_INVALIDO", f"Tipo de reporte desconocido: {tipo}")
    nombre, contenido = await generar_reporte(db, tipo, body.model_dump(exclude_unset=True), user)
    return StreamingResponse(iter([contenido]), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
