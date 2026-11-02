"""Persistencia y lectura de los criterios de clasificación por torneo.

Se guardan dentro de torneos.config_visibilidad para reutilizar el JSONB
existente y no romper datos históricos. El motor de clasificación los lee
desde ahí; las tablas rankings_* quedan solo como caché legacy.
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.rankings.engine import (
    config_clasificacion,
    criterios_label,
    compute_tournament_rankings,
    normalizar_criterios,
    normalizar_puntos,
    puntos_de_torneo,
)
from app.shared.errors import AppError
from app.torneos.models import Torneo


def get_clasificacion(torneo: Torneo) -> dict:
    cfg = config_clasificacion(torneo)
    criterios = normalizar_criterios(cfg.get("criterios"))
    return {
        "torneo_id": str(torneo.id),
        "criterios": criterios,
        "criterios_label": criterios_label(criterios),
        "puntos": puntos_de_torneo(torneo),
        "actualizado_en": cfg.get("actualizado_en"),
        "actualizado_por": cfg.get("actualizado_por"),
    }


async def guardar_clasificacion(
    db: AsyncSession,
    torneo: Torneo,
    user_id: str,
    criterios: list[str],
    puntos: dict | None = None,
) -> dict:
    if not criterios:
        raise AppError(400, "SIN_CRITERIOS", "Selecciona al menos un criterio de clasificación")
    criterios = normalizar_criterios(criterios)
    puntos = normalizar_puntos(puntos)
    vis = dict(torneo.config_visibilidad or {})
    vis["clasificacion"] = {
        "criterios": criterios,
        "puntos": puntos,
        "actualizado_en": datetime.now(timezone.utc).isoformat(),
        "actualizado_por": str(user_id),
    }
    torneo.config_visibilidad = vis
    await db.flush()

    # Ejecuta el motor para validar y dejar listas las tablas derivadas.
    rows = await compute_tournament_rankings(db, str(torneo.id))
    data = get_clasificacion(torneo)
    data["equipos_recalculados"] = len(rows)
    return data
