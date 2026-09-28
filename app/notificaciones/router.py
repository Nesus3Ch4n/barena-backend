from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.shared.database import get_db
from app.shared.security import get_current_user
from app.shared.errors import NotFound
from app.notificaciones.models import Notificacion

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


def _out(n: Notificacion) -> dict:
    return {"id": n.id, "tipo": n.tipo, "titulo": n.titulo, "cuerpo": n.cuerpo,
            "partido_id": n.partido_id, "leida": n.leida,
            "creada_en": n.creada_en.isoformat() if n.creada_en else None}


@router.get("", response_model=dict)
async def mias(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Notificacion).where(Notificacion.user_id == user.id).order_by(Notificacion.creada_en.desc()).limit(50))
    items = res.scalars().all()
    res2 = await db.execute(select(func.count()).where(Notificacion.user_id == user.id, Notificacion.leida == False))
    return {"success": True, "data": {"items": [_out(n) for n in items], "no_leidas": res2.scalar() or 0}, "error": None}


@router.patch("/{notif_id}/leida", response_model=dict)
async def marcar_leida(notif_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Notificacion).where(Notificacion.id == notif_id, Notificacion.user_id == user.id))
    n = res.scalar_one_or_none()
    if not n:
        raise NotFound("NOTIFICACION_NOT_FOUND", "Notificación no existe", {"id": notif_id})
    n.leida = True
    await db.flush()
    return {"success": True, "data": {"id": n.id, "leida": True}, "error": None}


async def crear_notificacion(db: AsyncSession, user_id: str, tipo: str, titulo: str, cuerpo: str = None, partido_id: str = None) -> None:
    db.add(Notificacion(user_id=user_id, tipo=tipo, titulo=titulo, cuerpo=cuerpo, partido_id=partido_id))
    await db.flush()
