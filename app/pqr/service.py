from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.pqr.models import PQR
from app.shared.errors import AppError, NotFound

TIPOS_PQR = ("peticion", "queja", "reclamo", "sugerencia", "felicitacion")
ESTADOS_PQR = ("abierta", "en_proceso", "cerrada")


async def radicar_pqr(db: AsyncSession, torneo_id: str, user_id: str, tipo: str, asunto: str, mensaje: str) -> dict:
    from app.torneos.models import Torneo
    if tipo not in TIPOS_PQR:
        raise AppError(400, "TIPO_INVALIDO", f"tipo debe ser uno de {list(TIPOS_PQR)}")
    res = await db.execute(select(Torneo).where(Torneo.id == torneo_id))
    if not res.scalar_one_or_none():
        raise NotFound("TORNEO_NOT_FOUND", "Torneo no existe", {"id": torneo_id})
    pqr = PQR(torneo_id=torneo_id, user_id=user_id, tipo=tipo,
              asunto=asunto.strip(), mensaje=mensaje.strip())
    db.add(pqr)
    await db.flush()
    return {"id": pqr.id, "estado": pqr.estado}


async def listar_pqr(db: AsyncSession, torneo_id: str, user_id: str, is_super: bool, is_org: bool = False) -> dict:
    from app.torneos.service import _torneo_para_jueces
    from app.auth.models import Profile
    await _torneo_para_jueces(db, torneo_id, user_id, is_super, is_org)
    res = await db.execute(select(PQR).where(PQR.torneo_id == torneo_id).order_by(PQR.creado_en.desc()).limit(200))
    filas = list(res.scalars().all())
    uids = {f.user_id for f in filas if f.user_id}
    res = await db.execute(select(Profile).where(Profile.id.in_(uids))) if uids else None
    noms = {p.id: p.nombre_completo for p in res.scalars().all()} if res is not None else {}
    items = [{"id": f.id, "tipo": f.tipo, "asunto": f.asunto, "mensaje": f.mensaje,
              "estado": f.estado, "respuesta": f.respuesta, "user_id": f.user_id,
              "nombre": noms.get(f.user_id),
              "creado_en": f.creado_en.isoformat() if f.creado_en else None} for f in filas]
    contadores = {"total": len(filas)}
    for e in ESTADOS_PQR:
        contadores[e] = sum(1 for f in filas if f.estado == e)
    return {"items": items, "contadores": contadores}


async def responder_pqr(db: AsyncSession, pqr_id: str, user_id: str, is_super: bool, is_org: bool = False,
                        estado: str | None = None, respuesta: str | None = None) -> dict:
    from app.torneos.service import _torneo_para_jueces
    res = await db.execute(select(PQR).where(PQR.id == pqr_id))
    pqr = res.scalar_one_or_none()
    if not pqr:
        raise NotFound("PQR_NOT_FOUND", "PQR no existe", {"id": pqr_id})
    await _torneo_para_jueces(db, pqr.torneo_id, user_id, is_super, is_org)
    if estado is not None:
        if estado not in ESTADOS_PQR:
            raise AppError(400, "ESTADO_INVALIDO", f"estado debe ser uno de {list(ESTADOS_PQR)}")
        pqr.estado = estado
    if respuesta is not None:
        pqr.respuesta = respuesta.strip() or None
    await db.flush()
    return {"id": pqr.id, "estado": pqr.estado}
