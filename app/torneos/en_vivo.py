"""Centro público de seguimiento en vivo.

Agrega, en una sola lectura pública y de solo lectura, el estado del torneo:
partidos en vivo (reutilizando live_snapshot), próximos, finalizados,
posiciones por grupo y ranking general. Respeta `publico` y
`config_visibilidad` sin exponer datos administrativos.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.atletas.models import Atleta
from app.equipos.models import Equipo
from app.partidos.models import Partido, PartidoEvento
from app.partidos.service import list_partidos_detalle, live_snapshot
from app.rankings.engine import (
    compute_general_rankings,
    compute_group_rankings,
    criterios_de_torneo,
    criterios_label,
)
from app.shared.errors import NotFound
from app.torneos.models import Categoria, Grupo, Rama, Torneo
from app.torneos.service import _estado_publico, visibilidad

SANCIONES = {
    "tarjeta_amarilla": "Tarjeta amarilla",
    "tarjeta_roja": "Tarjeta roja",
    "sancion": "Sanción",
    "descalificacion": "Descalificación",
}
TIEMPOS = {
    "tiempo_muerto": "Tiempo muerto",
    "tiempo_receso": "Receso",
    "tiempo_medico": "Tiempo médico",
}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None


def _rama_label(rama: Rama) -> str:
    return rama.nombre_custom or {"masc": "Masculino", "fem": "Femenino", "mixto": "Mixto"}.get(rama.tipo, rama.tipo)


async def _torneo_publico(db: AsyncSession, identificador: str) -> Torneo:
    """Acepta UUID o slug. Solo devuelve torneos publicados."""
    identificador = (identificador or "").strip()
    try:
        UUID(identificador)
        condicion = Torneo.id == identificador
    except ValueError:
        condicion = Torneo.slug == identificador
    res = await db.execute(select(Torneo).where(condicion, Torneo.publico == True))  # noqa: E712
    torneo = res.scalar_one_or_none()
    if not torneo:
        raise NotFound("TORNEO_NOT_PUBLIC", "Torneo no público o inexistente", {"id": identificador})
    return torneo


def _sets_resumen(partido: dict) -> dict:
    local = visit = 0
    detalle = []
    for s in partido.get("sets") or []:
        gano_local = s.get("ganador_id") == partido.get("local")
        if not s.get("ganador_id"):
            gano_local = (s.get("pts_local") or 0) > (s.get("pts_visitante") or 0)
        if gano_local:
            local += 1
        else:
            visit += 1
        detalle.append({
            "numero_set": s.get("numero_set"),
            "pts_local": s.get("pts_local"),
            "pts_visitante": s.get("pts_visitante"),
            "ganador_id": s.get("ganador_id"),
        })
    return {"local": local, "visitante": visit, "detalle": detalle}


def _set_en_evento(eventos: list[PartidoEvento], seq: int) -> int:
    return 1 + sum(1 for e in eventos if e.tipo == "set_ganado" and e.seq < seq)


def _detalle_eventos(
    eventos: list[PartidoEvento],
    snap: dict,
    ahora: datetime,
) -> dict:
    equipos = snap.get("equipos") or {}
    atletas = snap.get("atletas") or {}
    duraciones = snap.get("tiempos_duracion_seg") or {}
    local_id = snap["partido"].get("equipo_local_id")
    visit_id = snap["partido"].get("equipo_visit_id")
    nombres = {
        "local": (equipos.get(local_id) or {}).get("nombre", "Dupla local"),
        "visitante": (equipos.get(visit_id) or {}).get("nombre", "Dupla visitante"),
    }

    tarjetas = []
    tiempos = []
    for e in eventos:
        if e.tipo not in SANCIONES and e.tipo not in TIEMPOS:
            continue
        lado = e.lado if e.lado in ("local", "visitante") else None
        if not lado and e.atleta_id:
            atleta = atletas.get(e.atleta_id) or {}
            lado = "local" if atleta.get("equipo_id") == local_id else ("visitante" if atleta.get("equipo_id") == visit_id else None)
        item = {
            "id": e.id,
            "seq": e.seq,
            "tipo": e.tipo,
            "lado": lado,
            "dupla": nombres.get(lado) if lado else None,
            "atleta_id": e.atleta_id,
            "atleta": (atletas.get(e.atleta_id) or {}).get("nombre_completo") if e.atleta_id else None,
            "razon": e.razon,
            "set": _set_en_evento(eventos, e.seq),
            "creado_at": _iso(e.creado_at),
        }
        if e.tipo in SANCIONES:
            item["label"] = SANCIONES[e.tipo]
            if e.tipo == "sancion":
                item["label"] = str((e.extra or {}).get("tipo", "sanción")).replace("_", " ").capitalize()
            tarjetas.append(item)
        else:
            item["label"] = TIEMPOS[e.tipo]
            item["duracion_seg"] = int(duraciones.get(e.tipo) or 0)
            creado = _aware(e.creado_at)
            item["restante_seg"] = max(0, int((creado.timestamp() + item["duracion_seg"]) - ahora.timestamp())) if creado and item["duracion_seg"] else 0
            tiempos.append(item)

    # Un tiempo sigue activo si es el último evento registrado de juego y su
    # ventana de duración no ha vencido. Un punto/saque/set posterior lo cierra.
    activo = None
    if tiempos and snap["partido"].get("estado") == "en_juego":
        ultimo_t = max(tiempos, key=lambda x: x["seq"])
        cierre = {"punto", "set_ganado", "saque", "saque_inicial"}
        interrumpido = any(e.seq > ultimo_t["seq"] and e.tipo in cierre for e in eventos)
        if not interrumpido and ultimo_t["restante_seg"] > 0:
            activo = ultimo_t

    usados = {"local": 0, "visitante": 0}
    for t in tiempos:
        if t["lado"] in usados:
            usados[t["lado"]] += 1

    return {
        "tarjetas": tarjetas[-12:],
        "tiempos": tiempos[-12:],
        "tiempo_activo": activo,
        "tiempos_usados": usados,
    }


def _partido_card(
    p: dict,
    numero: int,
    categorias: dict,
    grupos: dict,
    nombres: dict,
    atletas_por_equipo: dict,
    meta: dict,
) -> dict:
    cat = categorias.get(p.get("categoria_id")) or {}
    grupo = grupos.get(p.get("grupo_id")) or {}
    resumen = _sets_resumen(p)
    local_id, visit_id = p.get("local"), p.get("visit")
    return {
        "id": p["id"],
        "numero": numero,
        "llave": p.get("llave") or 0,
        "fase": p.get("fase"),
        "grupo_id": p.get("grupo_id"),
        "grupo_nombre": grupo.get("nombre"),
        "categoria_id": p.get("categoria_id"),
        "categoria_nombre": cat.get("nombre"),
        "rama": cat.get("rama"),
        "cancha": p.get("cancha"),
        "fecha_hora": p.get("fecha_hora"),
        "estado": p.get("estado"),
        "ganador_id": p.get("ganador_id"),
        "iniciado_en": meta.get("iniciado_en"),
        "finalizado_en": meta.get("finalizado_en"),
        "local": {
            "id": local_id,
            "nombre": nombres.get(local_id, "Por definir"),
            "atletas": atletas_por_equipo.get(local_id, []),
        },
        "visitante": {
            "id": visit_id,
            "nombre": nombres.get(visit_id, "Por definir"),
            "atletas": atletas_por_equipo.get(visit_id, []),
        },
        "sets_ganados": {"local": resumen["local"], "visitante": resumen["visitante"]},
        "sets": resumen["detalle"],
    }


async def get_centro_en_vivo(db: AsyncSession, identificador: str) -> dict:
    torneo = await _torneo_publico(db, identificador)
    vis = visibilidad(torneo)
    ver_fixture = bool(vis.get("fixture_visible"))
    ver_posiciones = bool(vis.get("posiciones_visible") or vis.get("ranking_visible"))
    ver_ranking = bool(vis.get("ranking_visible"))
    criterio_torneo = criterios_label(criterios_de_torneo(torneo))
    ahora = _ahora()

    # Categorías y grupos del torneo (nombres y reglas para mostrar).
    cats_rows = (await db.execute(
        select(Rama, Categoria)
        .join(Categoria, Categoria.rama_id == Rama.id)
        .where(Rama.torneo_id == torneo.id)
        .order_by(Rama.tipo, Categoria.nombre)
    )).all()
    categorias = {
        c.id: {
            "id": c.id,
            "nombre": c.nombre,
            "rama": _rama_label(r),
            "rama_tipo": r.tipo,
            "formato": c.formato,
            "sets_x_partido": c.sets_x_partido,
            "puntos_x_set": c.puntos_x_set,
            "avance_x_grupo": c.avance_x_grupo,
            "clasificados": getattr(c, "clasificados", None),
            "criterio_clasif": getattr(c, "criterio_clasif", None),
            "ranking_general_enabled": bool(getattr(c, "ranking_general_enabled", True)),
        }
        for r, c in cats_rows
    }
    grupos_rows = (await db.execute(
        select(Grupo)
        .join(Categoria, Grupo.categoria_id == Categoria.id)
        .join(Rama, Categoria.rama_id == Rama.id)
        .where(Rama.torneo_id == torneo.id)
        .order_by(Categoria.nombre, Grupo.orden)
    )).scalars().all()
    grupos = {g.id: {"id": g.id, "nombre": g.nombre, "orden": g.orden, "categoria_id": g.categoria_id} for g in grupos_rows}

    equipos_rows = (await db.execute(
        select(Equipo)
        .join(Categoria, Equipo.categoria_id == Categoria.id)
        .join(Rama, Categoria.rama_id == Rama.id)
        .where(Rama.torneo_id == torneo.id)
    )).scalars().all()
    nombres = {e.id: e.nombre for e in equipos_rows}
    equipo_ids = list(nombres.keys())
    atletas_por_equipo: dict[str, list[dict]] = {eid: [] for eid in equipo_ids}
    if equipo_ids:
        atletas = (await db.execute(
            select(Atleta).where(Atleta.equipo_id.in_(equipo_ids)).order_by(Atleta.nombre_completo)
        )).scalars().all()
        for a in atletas:
            atletas_por_equipo.setdefault(a.equipo_id, []).append({"id": a.id, "nombre_completo": a.nombre_completo})

    # Partidos del torneo: solo si el fixture está publicado.
    partidos: list[dict] = []
    meta: dict[str, dict] = {}
    if ver_fixture:
        partidos = await list_partidos_detalle(db, torneo_id=torneo.id)
        ids = [p["id"] for p in partidos]
        if ids:
            filas = (await db.execute(
                select(Partido.id, Partido.iniciado_en, Partido.finalizado_en).where(Partido.id.in_(ids))
            )).all()
            meta = {f[0]: {"iniciado_en": _iso(f[1]), "finalizado_en": _iso(f[2])} for f in filas}

    ordenados = sorted(partidos, key=lambda p: (p.get("fecha_hora") or "9999", p.get("cancha") or "", p["id"]))
    numero = {p["id"]: i for i, p in enumerate(ordenados, start=1)}

    # ---- En vivo (incluye suspendidos para que se vea el estado en el tablero) ----
    vivos = [p for p in partidos if p.get("estado") == "en_juego"]
    suspendidos = [p for p in partidos if p.get("estado") == "suspendido"]
    activos = vivos + suspendidos
    activos.sort(key=lambda p: ((p.get("cancha") or "").lower(), p.get("fecha_hora") or "", numero[p["id"]]))
    eventos_por: dict[str, list[PartidoEvento]] = {}
    if activos:
        ids_vivos = [p["id"] for p in activos]
        eventos = (await db.execute(
            select(PartidoEvento)
            .where(PartidoEvento.partido_id.in_(ids_vivos), PartidoEvento.revocado == False)  # noqa: E712
            .order_by(PartidoEvento.partido_id, PartidoEvento.seq)
        )).scalars().all()
        for e in eventos:
            eventos_por.setdefault(e.partido_id, []).append(e)

    en_vivo = []
    for p in activos:
        try:
            snap = await live_snapshot(db, p["id"])
        except Exception:
            # Un partido en juego sin snapshot válido no debe tumbar el tablero.
            snap = {
                "partido": {"id": p["id"], "estado": p.get("estado"), "equipo_local_id": p.get("local"), "equipo_visit_id": p.get("visit")},
                "equipos": {k: {"id": k, "nombre": nombres.get(k, "Por definir")} for k in (p.get("local"), p.get("visit")) if k},
                "atletas": {}, "sets": p.get("sets") or [], "current_set": 1, "set_target": None,
                "score": {"local": 0, "visitante": 0}, "sets_ganados": {"local": 0, "visitante": 0},
                "saque": {"lado": None, "atleta_id": None}, "tiempos": {},
                "tiempos_duracion_seg": {}, "tarjetas": {}, "historial": [],
            }
        detalles = _detalle_eventos(eventos_por.get(p["id"], []), snap, ahora)
        cat = categorias.get(p["categoria_id"]) or {}
        grupo = grupos.get(p.get("grupo_id")) or {}
        en_vivo.append({
            **snap,
            "numero": numero[p["id"]],
            "categoria_id": p["categoria_id"],
            "categoria_nombre": cat.get("nombre"),
            "rama": cat.get("rama"),
            "grupo_id": p.get("grupo_id"),
            "grupo_nombre": grupo.get("nombre"),
            "fase": p.get("fase"),
            "cancha": p.get("cancha"),
            "fecha_hora": p.get("fecha_hora"),
            "sets_anteriores": _sets_resumen(p)["detalle"],
            "tarjetas_detalle": detalles["tarjetas"],
            "tiempos_detalle": detalles["tiempos"],
            "tiempo_activo": detalles["tiempo_activo"],
            "tiempos_usados": detalles["tiempos_usados"],
        })

    # ---- Próximos ----
    pendientes = [p for p in partidos if p.get("estado") == "pendiente"]
    programados = sorted(
        [p for p in pendientes if p.get("fecha_hora")],
        key=lambda p: (p["fecha_hora"], (p.get("cancha") or "").lower(), numero[p["id"]]),
    )
    sin_programar = [p for p in pendientes if not p.get("fecha_hora")]
    proximos = [
        _partido_card(p, numero[p["id"]], categorias, grupos, nombres, atletas_por_equipo, meta.get(p["id"], {}))
        for p in programados[:15]
    ]
    # Si aún no hay horarios, mostrar los pendientes sin programar.
    if not proximos:
        sin_hora = sorted(sin_programar, key=lambda p: ((p.get("cancha") or "").lower(), numero[p["id"]]))
        proximos = [
            _partido_card(p, numero[p["id"]], categorias, grupos, nombres, atletas_por_equipo, meta.get(p["id"], {}))
            for p in sin_hora[:15]
        ]

    # ---- Finalizados (ticker e historial) ----
    finalizados = [p for p in partidos if p.get("estado") == "finalizado"]
    finalizados.sort(
        key=lambda p: (meta.get(p["id"], {}).get("finalizado_en") or p.get("fecha_hora") or "", numero[p["id"]]),
        reverse=True,
    )
    recientes = [
        _partido_card(p, numero[p["id"]], categorias, grupos, nombres, atletas_por_equipo, meta.get(p["id"], {}))
        for p in finalizados[:20]
    ]

    # ---- Posiciones por grupo (motor centralizado, criterios del torneo) ----
    tablas: list[dict] = []
    if ver_posiciones:
        por_grupo: dict[str, list] = {}
        for cat in categorias.values():
            corte = cat.get("clasificados") or cat.get("avance_x_grupo") or 0
            for r in await compute_group_rankings(db, cat["id"]):
                por_grupo.setdefault(r["grupo_id"], []).append({
                    "posicion": r["posicion"],
                    "equipo_id": r["equipo_id"],
                    "equipo_nombre": r["equipo_nombre"] or nombres.get(r["equipo_id"], "Equipo"),
                    "pj": r["pj"],
                    "pg": r["pg"],
                    "pe": r["pe"],
                    "pp": r["pp"],
                    "pts": r["pts"],
                    "sets_favor": r["sets_favor"],
                    "sets_contra": r["sets_contra"],
                    "puntos_favor": r["puntos_favor"],
                    "puntos_contra": r["puntos_contra"],
                    "diferencia": r["puntos_favor"] - r["puntos_contra"],
                    "sanciones": r["sanciones"],
                    "clasifica": bool(corte) and (r["posicion"] or 0) <= corte,
                })
        for g in grupos_rows:
            cat = categorias.get(g.categoria_id) or {}
            tablas.append({
                "id": g.id,
                "nombre": g.nombre,
                "categoria_id": g.categoria_id,
                "categoria_nombre": cat.get("nombre"),
                "rama": cat.get("rama"),
                "criterio": criterio_torneo,
                "avance": cat.get("clasificados") or cat.get("avance_x_grupo") or 0,
                "posiciones": por_grupo.get(g.id, []),
            })

    # ---- Ranking general del torneo (mismo motor y criterios) ----
    ranking: list[dict] = []
    if ver_ranking:
        for cat in categorias.values():
            if not cat.get("ranking_general_enabled", True):
                continue
            for r in await compute_general_rankings(db, cat["id"]):
                ranking.append({
                    "equipo_id": r["equipo_id"],
                    "equipo_nombre": r["equipo_nombre"] or nombres.get(r["equipo_id"], "Equipo"),
                    "categoria_id": cat["id"],
                    "categoria_nombre": cat["nombre"],
                    "rama": cat["rama"],
                    "grupo_id": r["grupo_id"],
                    "grupo_nombre": r["grupo_nombre"],
                    "posicion_categoria": r["posicion"],
                    "pj": r["pj"],
                    "pg": r["pg"],
                    "pe": r["pe"],
                    "pp": r["pp"],
                    "pts": r["pts"],
                    "sets_favor": r["sets_favor"],
                    "sets_contra": r["sets_contra"],
                    "puntos_favor": r["puntos_favor"],
                    "puntos_contra": r["puntos_contra"],
                    "diferencia": r["puntos_favor"] - r["puntos_contra"],
                    "sanciones": r["sanciones"],
                })
        # Cada categoría conserva el orden oficial de su ranking general; no se
        # mezclan categorías con una fórmula nueva.
        ranking.sort(key=lambda x: ((x["categoria_nombre"] or "").lower(), x["posicion_categoria"] or 0, x["equipo_nombre"].lower()))
        for i, row in enumerate(ranking, start=1):
            row["posicion"] = i

    canchas = sorted({(p.get("cancha") or "").strip() for p in vivos if (p.get("cancha") or "").strip()}, key=str.lower)
    finalizados_n = len(finalizados)
    total = len(partidos)
    estado = _estado_publico(torneo, total, finalizados_n, len(vivos))

    fase_actual = None
    for p in (vivos or programados or pendientes or finalizados):
        fase_actual = p.get("fase")
        break
    if not fase_actual and finalizados:
        fase_actual = finalizados[0].get("fase")
    fecha_jornada = None
    for p in (vivos or programados or finalizados):
        fecha_jornada = p.get("fecha_hora")
        if fecha_jornada:
            break

    # Huella estable para que el cliente detecte cambios reales (incluye los
    # eventos de juego para no perder cambios dentro de un partido en vivo).
    huella = [
        [p["id"], p.get("estado"), p.get("cancha"), p.get("fecha_hora"), p.get("ganador_id"),
         [[s.get("numero_set"), s.get("pts_local"), s.get("pts_visitante")] for s in (p.get("sets") or [])]]
        for p in ordenados
    ]
    eventos_huella = {
        pid: [[e.id, e.seq, e.tipo, bool(e.revocado)] for e in evs]
        for pid, evs in eventos_por.items()
    }
    version = hashlib.md5(json.dumps([huella, eventos_huella], sort_keys=True, default=str).encode()).hexdigest()[:12]

    return {
        "torneo": {
            "id": torneo.id,
            "nombre": torneo.nombre,
            "slug": torneo.slug,
            "sede": torneo.sede,
            "ciudad": torneo.ciudad,
            "fecha_inicio": _iso(torneo.fecha_inicio),
            "fecha_fin": _iso(torneo.fecha_fin),
            "estado": estado,
            "publico": torneo.publico,
        },
        "secciones": {
            "fixture": ver_fixture,
            "grupos": bool(vis.get("grupos_visible")),
            "posiciones": ver_posiciones,
            "ranking": ver_ranking,
        },
        "resumen": {
            "total_partidos": total,
            "en_juego": len(vivos),
            "suspendidos": len(suspendidos),
            "finalizados": finalizados_n,
            "pendientes": len(pendientes),
            "sin_programar": len(sin_programar),
            "canchas_activas": len(canchas),
            "canchas": canchas,
            "fase_actual": fase_actual,
            "fecha_jornada": fecha_jornada,
        },
        "generado_en": ahora.isoformat(),
        "version": version,
        "en_vivo": en_vivo,
        "proximos": proximos,
        "finalizados": recientes,
        "tablas": tablas,
        "ranking_general": ranking,
    }
