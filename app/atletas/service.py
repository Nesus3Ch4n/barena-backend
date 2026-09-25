from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.atletas.models import Atleta
from app.torneos.models import Grupo
from app.shared.errors import NotFound

async def list_atletas_equipo(db: AsyncSession, equipo_id: str):
    res = await db.execute(select(Atleta).where(Atleta.equipo_id == equipo_id))
    return res.scalars().all()

async def get_atleta(db: AsyncSession, atleta_id: str):
    res = await db.execute(select(Atleta).where(Atleta.id == atleta_id))
    atleta = res.scalar_one_or_none()
    if not atleta:
        raise NotFound("ATLETA_NOT_FOUND", "Atleta no existe", {"id": atleta_id})
    return atleta

async def get_atleta_por_codigo(db: AsyncSession, codigo: str) -> dict:
    from app.equipos.models import Equipo
    from app.torneos.models import Categoria, Rama, Torneo
    cod = (codigo or "").strip().upper()
    res = await db.execute(select(Atleta).where(Atleta.codigo_reclamo == cod))
    atl = res.scalar_one_or_none()
    if not atl:
        raise NotFound("ATLETA_NOT_FOUND", "Código no registrado", {"codigo": cod})
    res2 = await db.execute(select(Equipo).where(Equipo.id == atl.equipo_id))
    eq = res2.scalar_one_or_none()
    torneo_nombre, categoria_nombre = None, None
    if eq:
        res3 = await db.execute(select(Categoria).where(Categoria.id == eq.categoria_id))
        cat = res3.scalar_one_or_none()
        if cat:
            categoria_nombre = cat.nombre
            res4 = await db.execute(select(Rama).where(Rama.id == cat.rama_id))
            rama = res4.scalar_one_or_none()
            if rama:
                res5 = await db.execute(select(Torneo).where(Torneo.id == rama.torneo_id))
                tor = res5.scalar_one_or_none()
                if tor:
                    torneo_nombre = tor.nombre
    return {"id": atl.id, "nombre_completo": atl.nombre_completo, "posicion": atl.posicion,
            "codigo_reclamo": atl.codigo_reclamo, "tiene_cuenta": bool(atl.user_id),
            "equipo_nombre": eq.nombre if eq else None, "categoria_nombre": categoria_nombre,
            "torneo_nombre": torneo_nombre}
