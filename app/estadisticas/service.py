from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.estadisticas.models import EstadisticaAtleta
from app.partidos.models import Partido
from app.atletas.models import Atleta
from app.shared.errors import AppError, NotFound
from app.estadisticas.schemas import EstadisticaIn

async def upsert_estadistica(db: AsyncSession, partido_id: str, data: EstadisticaIn) -> EstadisticaAtleta:
    # validate partido exists and not pendiente? allow en_juego
    res = await db.execute(select(Partido).where(Partido.id == partido_id))
    partido = res.scalar_one_or_none()
    if not partido:
        raise NotFound("PARTIDO_NOT_FOUND", "Partido no existe", {"id": partido_id})
    # validate atleta belongs to one of the teams in partido
    res2 = await db.execute(select(Atleta).where(Atleta.id == data.atleta_id))
    atleta = res2.scalar_one_or_none()
    if not atleta:
        raise NotFound("ATLETA_NOT_FOUND", "Atleta no existe", {"id": data.atleta_id})
    if atleta.equipo_id not in (partido.equipo_local_id, partido.equipo_visit_id):
        raise AppError(400, "ATLETA_NO_EN_PARTIDO", "Atleta no pertenece a este partido")
    # upsert
    res3 = await db.execute(select(EstadisticaAtleta).where(EstadisticaAtleta.atleta_id == data.atleta_id, EstadisticaAtleta.partido_id == partido_id))
    existing = res3.scalar_one_or_none()
    if existing:
        for k, v in data.model_dump().items():
            if k == "atleta_id": continue
            setattr(existing, k, v)
        await db.flush()
        return existing
    else:
        est = EstadisticaAtleta(partido_id=partido_id, atleta_id=data.atleta_id, ataques_pts=data.ataques_pts, bloqueos_pts=data.bloqueos_pts, saques_directos=data.saques_directos, errores_propios=data.errores_propios, defensas_dig=data.defensas_dig, recepciones_perf=data.recepciones_perf, ataques_total=data.ataques_total, saques_total=data.saques_total)
        db.add(est)
        await db.flush()
        return est

async def list_estadisticas(db: AsyncSession, partido_id: str):
    res = await db.execute(select(EstadisticaAtleta).where(EstadisticaAtleta.partido_id == partido_id))
    return res.scalars().all()

async def get_atleta_stats(db: AsyncSession, atleta_id: str) -> dict:
    res = await db.execute(select(EstadisticaAtleta).where(EstadisticaAtleta.atleta_id == atleta_id))
    stats = res.scalars().all()
    total_pts = sum(s.ataques_pts + s.bloqueos_pts + s.saques_directos for s in stats)
    total_atk = sum(s.ataques_pts for s in stats)
    total_blk = sum(s.bloqueos_pts for s in stats)
    total_ace = sum(s.saques_directos for s in stats)
    total_err = sum(s.errores_propios for s in stats)
    total_dig = sum(s.defensas_dig for s in stats)
    total_ataques = sum(s.ataques_total for s in stats)
    total_saques = sum(s.saques_total for s in stats)
    eft_atk = round((total_atk / (total_ataques - total_err) * 100) if (total_ataques - total_err) > 0 else 0, 2)
    eft_saq = round((total_ace / total_saques * 100) if total_saques > 0 else 0, 2)
    return {"atleta_id": atleta_id, "partidos": len(stats), "total_pts": total_pts, "atk": total_atk, "blk": total_blk, "ace": total_ace, "err": total_err, "dig": total_dig, "eft_atk": eft_atk, "eft_saq": eft_saq, "stats": [{"partido_id": s.partido_id, "ataques_pts": s.ataques_pts, "bloqueos_pts": s.bloqueos_pts, "saques_directos": s.saques_directos} for s in stats]}
