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

def _evento_contexto(eventos, seq_objetivo: int) -> dict:
    ult_set, n_set, sl, sv = 0, 1, 0, 0
    for e in eventos:
        if e.seq > seq_objetivo:
            break
        if e.tipo == "set_ganado":
            ult_set, n_set = e.seq, n_set + 1
    for e in eventos:
        if e.tipo == "punto" and e.seq > ult_set and e.seq <= seq_objetivo:
            if e.lado == "local":
                sl += 1
            else:
                sv += 1
    return {"set": n_set, "marcador": f"{sl}-{sv}"}


async def get_atleta_resumen(db: AsyncSession, atleta_id: str) -> dict:
    from app.equipos.models import Equipo
    from app.torneos.models import Categoria, Rama, Torneo
    from app.partidos.models import Partido, PartidoEvento
    from app.rankings.models import RankingGeneral
    base = await get_atleta_stats(db, atleta_id)
    res = await db.execute(select(Atleta).where(Atleta.id == atleta_id))
    atl = res.scalar_one_or_none()
    if not atl:
        raise NotFound("ATLETA_NOT_FOUND", "Atleta no existe", {"id": atleta_id})
    # todas las filas vinculadas a la misma cuenta (o solo esta)
    comp_ids = [atl.user_id] if atl.user_id else []
    if comp_ids:
        res = await db.execute(select(Atleta).where(Atleta.user_id == atl.user_id))
        filas = list(res.scalars().all())
    else:
        filas = [atl]
    eq_ids = list({f.equipo_id for f in filas})
    res = await db.execute(select(Equipo).where(Equipo.id.in_(eq_ids))) if eq_ids else None
    equipos = list(res.scalars().all()) if res is not None else []
    torneos, pj, pg = [], 0, 0
    for eq in equipos:
        res = await db.execute(select(Partido).where(
            ((Partido.equipo_local_id == eq.id) | (Partido.equipo_visit_id == eq.id)),
            Partido.estado == "finalizado"))
        parts = list(res.scalars().all())
        w = sum(1 for p in parts if p.ganador_id == eq.id)
        pj += len(parts)
        pg += w
        res = await db.execute(select(Categoria).where(Categoria.id == eq.categoria_id))
        cat = res.scalar_one_or_none()
        tor_nom, desenlace, fase = None, "en_curso", None
        if cat:
            res = await db.execute(select(Rama).where(Rama.id == cat.rama_id))
            rama = res.scalar_one_or_none()
            if rama:
                res = await db.execute(select(Torneo).where(Torneo.id == rama.torneo_id))
                tor = res.scalar_one_or_none()
                if tor:
                    tor_nom = tor.nombre
            gano_final = any(p.fase == "final" and p.ganador_id == eq.id for p in parts)
            elim = [p for p in parts if p.fase != "grupos"]
            if gano_final:
                desenlace = "ganado"
            elif elim:
                orden_f = {"final": 6, "semi": 5, "cuartos": 4, "octavos": 3, "tercer_puesto": 2}
                top = max(elim, key=lambda p: orden_f.get(p.fase, 1))
                desenlace, fase = "eliminado", top.fase
            else:
                res = await db.execute(select(RankingGeneral).where(
                    RankingGeneral.categoria_id == eq.categoria_id,
                    RankingGeneral.equipo_id == eq.id))
                rk = res.scalar_one_or_none()
                res = await db.execute(select(Categoria).where(Categoria.id == eq.categoria_id))
                cupo = getattr(res.scalar_one_or_none(), "clasificados", None)
                if rk and cupo and (rk.posicion or 999) > cupo:
                    desenlace = "no_clasificado"
        torneos.append({"equipo_id": eq.id, "equipo_nombre": eq.nombre, "torneo": tor_nom,
                        "categoria_id": eq.categoria_id, "desenlace": desenlace, "fase": fase,
                        "pj": len(parts), "pg": w, "pp": len(parts) - w})
    res = await db.execute(select(PartidoEvento).where(
        PartidoEvento.atleta_id == atleta_id,
        PartidoEvento.tipo.in_(["tarjeta_amarilla", "tarjeta_roja", "sancion", "descalificacion"]),
        PartidoEvento.revocado == False).order_by(PartidoEvento.creado_at.desc()))
    sancs = []
    for e in res.scalars().all():
        ctx = {"set": 1, "marcador": ""}
        if e.partido_id:
            r2 = await db.execute(select(PartidoEvento).where(
                PartidoEvento.partido_id == e.partido_id).order_by(PartidoEvento.seq))
            ctx = _evento_contexto(list(r2.scalars().all()), e.seq)
        sancs.append({"tipo": e.tipo, "razon": e.razon, "partido_id": e.partido_id,
                      "set": ctx["set"], "marcador": ctx["marcador"],
                      "creada_en": e.creado_at.isoformat() if e.creado_at else None})
    return {**base, "torneos": torneos, "partidos_totales": pj, "partidos_ganados": pg,
            "partidos_perdidos": pj - pg, "sanciones": sancs}


async def get_juez_resumen(db: AsyncSession, user_id: str) -> dict:
    from app.torneos.models import Categoria, Rama, Torneo
    from app.partidos.models import Partido
    res = await db.execute(select(Partido).where(Partido.arbitro_id == str(user_id)))
    parts = list(res.scalars().all())
    por_torneo: dict = {}
    arb, por_arb = 0, 0
    for p in parts:
        if p.estado == "finalizado":
            arb += 1
        else:
            por_arb += 1
        res = await db.execute(select(Categoria).where(Categoria.id == p.categoria_id))
        cat = res.scalar_one_or_none()
        tnom = None
        if cat:
            res = await db.execute(select(Rama).where(Rama.id == cat.rama_id))
            rama = res.scalar_one_or_none()
            if rama:
                res = await db.execute(select(Torneo).where(Torneo.id == rama.torneo_id))
                tor = res.scalar_one_or_none()
                if tor:
                    tnom = tor.nombre
        por_torneo[tnom or "—"] = por_torneo.get(tnom or "—", 0) + 1
    return {"arbitrados": arb, "por_arbitrar": por_arb, "total": len(parts),
            "por_torneo": [{"torneo": k, "partidos": v} for k, v in por_torneo.items()],
            "proximos": [{"id": p.id, "fase": p.fase, "cancha": p.cancha,
                          "fecha_hora": p.fecha_hora.isoformat() if p.fecha_hora else None,
                          "estado": p.estado}
                         for p in sorted(parts, key=lambda x: (x.fecha_hora is None, x.fecha_hora))
                         if p.estado != "finalizado"][:10]}


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
    eft_atk = round((total_atk / total_ataques * 100) if total_ataques > 0 else 0, 2)
    eft_saq = round((total_ace / total_saques * 100) if total_saques > 0 else 0, 2)
    return {"atleta_id": atleta_id, "partidos": len(stats), "total_pts": total_pts, "atk": total_atk, "blk": total_blk, "ace": total_ace, "err": total_err, "dig": total_dig, "eft_atk": eft_atk, "eft_saq": eft_saq, "stats": [{"partido_id": s.partido_id, "ataques_pts": s.ataques_pts, "bloqueos_pts": s.bloqueos_pts, "saques_directos": s.saques_directos} for s in stats]}
