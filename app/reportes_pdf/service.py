"""Generación de reportes PDF (descargables) para organizador, atleta y juez."""
import io
from datetime import datetime, timezone
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak, Flowable)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.errors import AppError, NotFound, Forbidden
from app.reportes_pdf.charts import barras, dona, lineas

NAVY = colors.HexColor("#0a2a35")
CORAL = colors.HexColor("#e07856")
GRIS = colors.HexColor("#75838a")

EST_TITULO = ParagraphStyle("tit", fontName="Helvetica-Bold", fontSize=18, textColor=NAVY, spaceAfter=4)
EST_H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, textColor=CORAL, spaceBefore=10, spaceAfter=4)
EST_TXT = ParagraphStyle("txt", fontName="Helvetica", fontSize=9, textColor=colors.black, spaceAfter=3)
EST_CENTRO = ParagraphStyle("cen", parent=EST_TXT, alignment=TA_CENTER)
EST_TABLA_CELDA = ParagraphStyle("cel", fontName="Helvetica", fontSize=8, textColor=colors.black)
EST_TABLA_HEAD = ParagraphStyle("celh", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white)


def _ahora_str() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


class _Dibujo(Flowable):
    def __init__(self, drawing, w=460, h=130):
        super().__init__()
        self.drawing = drawing
        self.width, self.height = w, h

    def draw(self):
        self.drawing.drawOn(self.canv, 0, 0)


def _tabla(datos, anchos, cabeza=True):
    filas = []
    for i, fila in enumerate(datos):
        celdas = []
        for v in fila:
            st = EST_TABLA_HEAD if (cabeza and i == 0) else EST_TABLA_CELDA
            celdas.append(Paragraph(str(v), st))
        filas.append(celdas)
    t = Table(filas, colWidths=anchos, repeatRows=1 if cabeza else 0)
    estilo = [("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dfe7e5")),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 4),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if cabeza:
        estilo += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    t.setStyle(TableStyle(estilo))
    return t


def _doc(titulo: str):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=36, rightMargin=36,
                            topMargin=36, bottomMargin=36, title=titulo)
    return buf, doc


def _portada(cuerpo: list, kicker: str, titulo: str, lineas: list):
    cuerpo.append(Paragraph("BARENA · BEACH VOLLEY", ParagraphStyle("kick", parent=EST_TXT, textColor=CORAL, fontName="Helvetica-Bold", fontSize=9)))
    cuerpo.append(Paragraph(kicker, EST_TXT))
    cuerpo.append(Paragraph(titulo, EST_TITULO))
    for lin in lineas:
        cuerpo.append(Paragraph(lin, EST_TXT))
    cuerpo.append(Paragraph(f"Generado: {_ahora_str()}", EST_TXT))
    cuerpo.append(Spacer(1, 0.15 * inch))


async def generar_reporte(db: AsyncSession, tipo: str, params: dict, user) -> tuple:
    from app.estadisticas.service import get_atleta_resumen, get_juez_resumen
    roles = list(getattr(user, "roles_cache", []) or [])
    if not roles:
        try:
            from app.auth.service import get_roles_for_user
            roles = await get_roles_for_user(db, user.id)
        except Exception:
            roles = []
    es_staff = "organizador" in roles or "super_admin" in roles

    if tipo == "perfil_atleta":
        atleta_id = (params or {}).get("atleta_id")
        if not atleta_id:
            raise AppError(400, "PARAM_FALTANTE", "atleta_id requerido")
        if not es_staff:
            from app.atletas.models import Atleta
            res = await db.execute(select(Atleta).where(Atleta.id == atleta_id))
            atl = res.scalar_one_or_none()
            if not atl or str(atl.user_id or "") != str(user.id):
                raise Forbidden("Solo puedes ver tu propio reporte")
        datos = await get_atleta_resumen(db, atleta_id)
        return _pdf_perfil_atleta(datos)
    if tipo == "perfil_juez":
        uid = (params or {}).get("user_id") or str(user.id)
        if not es_staff and str(uid) != str(user.id):
            raise Forbidden("Solo puedes ver tu propio reporte")
        datos = await get_juez_resumen(db, uid)
        return _pdf_perfil_juez(datos, uid)
    if tipo in ("parcial", "final"):
        if not es_staff:
            raise Forbidden("Solo el organizador genera informes del evento")
        torneo_id = (params or {}).get("torneo_id")
        if not torneo_id:
            raise AppError(400, "PARAM_FALTANTE", "torneo_id requerido")
        return await _pdf_evento(db, tipo, torneo_id)
    if tipo == "partido":
        partido_id = (params or {}).get("partido_id")
        if not partido_id:
            raise AppError(400, "PARAM_FALTANTE", "partido_id requerido")
        return await _pdf_partido(db, partido_id, es_staff)
    raise AppError(400, "TIPO_INVALIDO", f"Tipo de reporte desconocido: {tipo}")


def _pdf_perfil_atleta(d: dict):
    cuerpo: list = []
    nombre = ""
    _portada(cuerpo, "PERFIL DEL ATLETA", "Reporte del deportista",
             [f"Generado: {_ahora_str()}"])
    cuerpo.append(Paragraph("Números", EST_H2))
    cuerpo.append(_tabla(
        [["Partidos", "Ganados", "Perdidos", "Win %"],
         [d.get("partidos_totales", 0), d.get("partidos_ganados", 0), d.get("partidos_perdidos", 0),
          f"{round(100 * d.get('partidos_ganados', 0) / max(1, d.get('partidos_totales', 0)))}%"]],
        [110, 110, 110, 110]))
    cuerpo.append(Paragraph("Acciones", EST_H2))
    cuerpo.append(_Dibujo(barras([
        ("ACE", d.get("ace", 0)), ("Ataques", d.get("atk", 0)), ("Bloqueos", d.get("blk", 0)),
        ("Defensas", d.get("dig", 0)), ("Errores", d.get("err", 0))])))
    tot_e = (d.get("atk", 0) + d.get("err", 0)) or 0
    tot_s = (d.get("ace", 0) + d.get("err", 0)) or 0
    cuerpo.append(Paragraph(
        f"Ataques efectivos: {d.get('atk', 0)} · Efectividad ataque: {round(100 * d.get('atk', 0) / max(1, tot_e))}% · "
        f"Saques directos: {d.get('ace', 0)} · Efectividad saque: {round(100 * d.get('ace', 0) / max(1, tot_s))}% · "
        f"Puntos totales: {d.get('total_pts', 0)}", EST_TXT))
    cuerpo.append(Paragraph("Partidos", EST_H2))
    cuerpo.append(_Dibujo(dona([
        ("Ganados", d.get("partidos_ganados", 0)), ("Perdidos", d.get("partidos_perdidos", 0))]),
        h=150))
    cuerpo.append(Paragraph("Torneos", EST_H2))
    filas = [["Torneo", "Dupla", "Desenlace", "PJ", "PG", "PP"]]
    for t in d.get("torneos", []):
        filas.append([t.get("torneo") or "—", (t.get("equipo_nombre") or "")[:28], t.get("desenlace", ""),
                      t.get("pj", 0), t.get("pg", 0), t.get("pp", 0)])
    cuerpo.append(_tabla(filas, [150, 130, 60, 30, 30, 30]) if len(filas) > 1 else Paragraph("Sin torneos registrados.", EST_TXT))
    des = {}
    for t in d.get("torneos", []):
        des[t.get("desenlace", "en_curso")] = des.get(t.get("desenlace", "en_curso"), 0) + 1
    if des:
        cuerpo.append(_Dibujo(dona([(k, v) for k, v in des.items()]), h=150))
    cuerpo.append(Paragraph("Sanciones", EST_H2))
    sancs = d.get("sanciones", [])
    if not sancs:
        cuerpo.append(Paragraph("Sin sanciones registradas.", EST_TXT))
    else:
        por_tipo: dict = {}
        for s in sancs:
            por_tipo[s.get("tipo", "?")] = por_tipo.get(s.get("tipo", "?"), 0) + 1
        cuerpo.append(_Dibujo(barras([(k, v) for k, v in por_tipo.items()]), h=120))
        filas = [["Tipo", "Motivo", "Set", "Marcador", "Fecha"]]
        for s in sancs[:20]:
            filas.append([s.get("tipo", ""), (s.get("razon") or "")[:20], s.get("set", ""),
                          s.get("marcador", ""), (s.get("creada_en") or "")[:16]])
        cuerpo.append(_tabla(filas, [110, 110, 40, 60, 120]))
    buf, doc = _doc("Reporte atleta")
    doc.build(cuerpo)
    return f"reporte_atleta_{d.get('atleta_id', 'x')[:8]}.pdf", buf.getvalue()


def _pdf_perfil_juez(d: dict, uid: str):
    cuerpo: list = []
    _portada(cuerpo, "PERFIL DEL JUEZ", "Reporte del juez",
             [f"Arbitrados: {d.get('arbitrados', 0)} · Por arbitrar: {d.get('por_arbitrar', 0)} · Total: {d.get('total', 0)}"])
    cuerpo.append(Paragraph("Por torneo", EST_H2))
    filas = [["Torneo", "Partidos"]]
    for t in d.get("por_torneo", []):
        filas.append([t.get("torneo") or "—", t.get("partidos", 0)])
    cuerpo.append(_tabla(filas, [330, 110]) if len(filas) > 1 else Paragraph("Sin partidos asignados.", EST_TXT))
    if d.get("por_torneo"):
        cuerpo.append(_Dibujo(barras([((t.get("torneo") or "-")[:22], t.get("partidos", 0)) for t in d["por_torneo"]])))
    cuerpo.append(Paragraph("Próximos", EST_H2))
    prox = d.get("proximos", [])
    if not prox:
        cuerpo.append(Paragraph("Sin partidos pendientes.", EST_TXT))
    else:
        filas = [["Fase", "Cancha", "Fecha", "Estado"]]
        for p in prox[:15]:
            filas.append([p.get("fase", ""), p.get("cancha") or "—", (p.get("fecha_hora") or "")[:16], p.get("estado", "")])
        cuerpo.append(_tabla(filas, [110, 80, 130, 120]))
    buf, doc = _doc("Reporte juez")
    doc.build(cuerpo)
    return f"reporte_juez_{str(uid)[:8]}.pdf", buf.getvalue()


async def _pdf_evento(db: AsyncSession, tipo: str, torneo_id: str):
    from app.torneos.service import get_torneo_detail
    from app.rankings.service import list_rankings_categoria_grupo, list_rankings_general
    det = await get_torneo_detail(db, torneo_id)
    tor = det["torneo"]
    cuerpo: list = []
    _portada(cuerpo, f"INFORME {tipo.upper()} DEL EVENTO", tor.nombre,
             [f"Sede: {tor.sede or '—'} · Ciudad: {tor.ciudad or '—'}",
              f"Estado: {tor.estado} · Público: {'sí' if tor.publico else 'no'}"])
    for rama, cats in det["ramas"]:
        for cat in cats:
            cuerpo.append(Paragraph(f"{rama.tipo} · {cat.nombre}", EST_H2))
            rg = await list_rankings_general(db, cat.id)
            if rg:
                from app.equipos.models import Equipo
                res_eq = await db.execute(select(Equipo).where(Equipo.id.in_([r.equipo_id for r in rg])))
                _noms = {e.id: e.nombre for e in res_eq.scalars().all()}
                filas = [["Pos", "Dupla", "PJ", "PG", "Pts"]]
                for r in rg[:16]:
                    filas.append([r.posicion, (_noms.get(r.equipo_id, "Equipo"))[:34], r.pj, r.pg, r.pts])
                cuerpo.append(_tabla(filas, [40, 220, 40, 40, 40]))
            else:
                cuerpo.append(Paragraph("Sin clasificación todavía.", EST_TXT))
            try:
                from app.partidos.service import list_partidos
                ps = await list_partidos(db, torneo_id, cat.id, None, None, None)
                fin = sum(1 for p in ps if p.estado == "finalizado")
                cuerpo.append(Paragraph(
                    f"Partidos: {len(ps)} en total · {fin} finalizados · {len(ps) - fin} pendientes.", EST_TXT))
                elim = [p for p in ps if p.fase != "grupos"]
                if elim:
                    filas = [["Fase", "Estado"]]
                    from collections import Counter
                    for (f, e), n in sorted(Counter((p.fase, p.estado) for p in elim).items()):
                        filas.append([f, f"{e}: {n}"])
                    cuerpo.append(_tabla(filas, [220, 220]))
            except Exception:
                pass
    buf, doc = _doc(f"Informe {tipo}")
    doc.build(cuerpo)
    return f"informe_{tipo}_{tor.slug}.pdf", buf.getvalue()


async def _pdf_partido(db: AsyncSession, partido_id: str, es_staff: bool):
    from app.partidos.service import get_partido, live_snapshot
    from app.equipos.models import Equipo
    partido, sets = await get_partido(db, partido_id)
    nombres = {}
    for eid in (partido.equipo_local_id, partido.equipo_visit_id):
        if eid:
            res = await db.execute(select(Equipo).where(Equipo.id == eid))
            eq = res.scalar_one_or_none()
            nombres[eid] = eq.nombre if eq else "Por definir"
    cuerpo: list = []
    _portada(cuerpo, "REPORTE DE PARTIDO",
             f"{nombres.get(partido.equipo_local_id, '?')} vs {nombres.get(partido.equipo_visit_id, '?')}",
             [f"Fase: {partido.fase} · Cancha: {partido.cancha or '—'} · Estado: {partido.estado}",
              f"Fecha: {partido.fecha_hora.isoformat()[:16] if partido.fecha_hora else '—'}"])
    cuerpo.append(Paragraph("Sets", EST_H2))
    if not sets:
        cuerpo.append(Paragraph("Sin sets registrados.", EST_TXT))
    else:
        filas = [["Set", "Local", "Visita", "Ganador"]]
        for s in sets:
            g = nombres.get(s.ganador_id, "—") if s.ganador_id else "—"
            filas.append([s.numero_set, s.pts_local, s.pts_visitante, (g or "")[:28]])
        cuerpo.append(_tabla(filas, [50, 80, 80, 230]))
    try:
        snap = await live_snapshot(db, partido_id)
        cuerpo.append(Paragraph("Desarrollo", EST_H2))
        cuerpo.append(Paragraph(
            f"Marcador actual: {snap['score']['local']}-{snap['score']['visitante']} · Set {snap['current_set']}", EST_TXT))
        ind = snap.get("individuales", {})
        if ind:
            filas = [["Atleta", "ACE", "ATQ", "BLQ", "DEF", "ERR"]]
            for aid, v in ind.items():
                nm = (snap.get("atletas", {}).get(aid) or {}).get("nombre_completo", "")[:26]
                filas.append([nm, v.get("saque_directo", 0), v.get("ataque", 0), v.get("bloqueo", 0),
                              v.get("defensa", 0), (v.get("error_saque", 0) + v.get("error_ataque", 0))])
            cuerpo.append(_tabla(filas, [170, 45, 45, 45, 45, 45]))
        if snap.get("observaciones"):
            cuerpo.append(Paragraph("Observaciones del juez", EST_H2))
            cuerpo.append(Paragraph(snap["observaciones"], EST_TXT))
    except Exception:
        pass
    obs = getattr(partido, "observaciones", None)
    if obs:
        cuerpo.append(Paragraph("Observaciones", EST_H2))
        cuerpo.append(Paragraph(obs, EST_TXT))
    buf, doc = _doc("Reporte partido")
    doc.build(cuerpo)
    return f"reporte_partido_{str(partido_id)[:8]}.pdf", buf.getvalue()
