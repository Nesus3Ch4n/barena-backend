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
    from app.partidos.service import get_partido
    partido, sets = await get_partido(db, partido_id)
    datos = await _datos_voley(db, partido, sets)
    buf = io.BytesIO()
    _construir_pdf_voley(buf, datos)
    return f"reporte_partido_{str(partido_id)[:8]}.pdf", buf.getvalue()


# ============================================================
# Reporte de partido estilo hoja oficial ("Volleyball Referee")
# A4 horizontal (841.9 x 595), 3 bloques: portada+set1 / sets / resumen.
# Usa UNICAMENTE datos reales: sets_partido + bitacora partido_eventos.
# ============================================================
_V_PW, _V_PH = 841.92, 594.96
_V_ROJO = colors.HexColor("#bc0018")
_V_NEGRO = colors.HexColor("#1f1f1f")
_V_GRIS = colors.HexColor("#ecebec")
_V_LINEA = colors.HexColor("#1f1f1f")

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _v_y(y: float) -> float:
    return _V_PH - y


def _v_fecha(dt) -> str:
    if not dt:
        return "—"
    return f"{_DIAS[dt.weekday()]}, {dt.day} de {_MESES[dt.month - 1]} de {dt.year}"


def _v_hora(dt) -> str:
    if not dt:
        return "—"
    h = dt.hour % 12 or 12
    suf = "a.m." if dt.hour < 12 else "p.m."
    return f"{h}:{dt.minute:02d} {suf}"


def _v_dur(a, b) -> str:
    if not a or not b:
        return "—"
    m = max(0, int(round((b - a).total_seconds() / 60)))
    return f"{m} min"


def _v_apellido(nombre: str) -> str:
    parts = (nombre or "").strip().split()
    return parts[-1] if parts else "—"


async def _datos_voley(db: AsyncSession, partido, sets: list) -> dict:
    from app.equipos.models import Equipo
    from app.atletas.models import Atleta
    from app.partidos.models import PartidoEvento
    from app.torneos.models import Categoria, Rama, Torneo, TorneoJuez
    from app.auth.models import User, Profile

    nombres = {}
    for eid in (partido.equipo_local_id, partido.equipo_visit_id):
        if eid:
            res = await db.execute(select(Equipo).where(Equipo.id == eid))
            eq = res.scalar_one_or_none()
            nombres[eid] = eq.nombre if eq else "Por definir"

    ats: dict = {}
    if partido.equipo_local_id or partido.equipo_visit_id:
        res = await db.execute(select(Atleta).where(Atleta.equipo_id.in_(
            [e for e in (partido.equipo_local_id, partido.equipo_visit_id) if e])).order_by(Atleta.nombre_completo))
        for at in res.scalars().all():
            ats.setdefault(at.equipo_id, []).append(
                {"id": at.id, "nombre": at.nombre_completo, "posicion": at.posicion})

    cat_nom, tor_nom = "—", "—"
    res = await db.execute(select(Categoria).where(Categoria.id == partido.categoria_id))
    cat = res.scalar_one_or_none()
    if cat:
        cat_nom = cat.nombre or "—"
        res = await db.execute(select(Rama).where(Rama.id == cat.rama_id))
        rama = res.scalar_one_or_none()
        if rama:
            res = await db.execute(select(Torneo).where(Torneo.id == rama.torneo_id))
            tor = res.scalar_one_or_none()
            if tor:
                tor_nom = tor.nombre or "—"

    res = await db.execute(select(PartidoEvento).where(
        PartidoEvento.partido_id == partido.id).order_by(PartidoEvento.seq))
    evs = [e for e in res.scalars().all() if not e.revocado]

    # Ventanas por set: todo lo ocurrido hasta cada 'set_ganado'
    ventanas: list = []
    ini = 0
    for e in evs:
        if e.tipo == "set_ganado":
            ventanas.append([x for x in evs if ini < x.seq <= e.seq])
            ini = e.seq
    resto = [x for x in evs if x.seq > ini and x.tipo in (
        "punto", "tiempo_muerto", "tiempo_receso", "tiempo_medico",
        "tarjeta_amarilla", "tarjeta_roja", "sancion", "descalificacion")]
    if resto:
        ventanas.append([x for x in evs if x.seq > ini])

    atl_nom = {}
    for lst in ats.values():
        for a in lst:
            atl_nom[a["id"]] = a["nombre"]

    bloques = []
    for i, win in enumerate(ventanas):
        num = i + 1
        arch = next((s for s in sets if s.numero_set == num), None)
        rallys = [x.lado for x in win if x.tipo == "punto" and x.lado in ("local", "visitante")]
        sl = sum(1 for l in rallys if l == "local")
        sv = sum(1 for l in rallys if l == "visitante")
        if arch:
            sl, sv = arch.pts_local, arch.pts_visitante
        # tiempos con marcador al momento del cobro
        tiempos = []
        for x in win:
            if x.tipo in ("tiempo_muerto", "tiempo_receso", "tiempo_medico") and x.lado in ("local", "visitante"):
                a = sum(1 for p in win if p.tipo == "punto" and p.seq < x.seq and p.lado == "local")
                b = sum(1 for p in win if p.tipo == "punto" and p.seq < x.seq and p.lado == "visitante")
                tiempos.append({"lado": x.lado, "tipo": x.tipo, "score": f"{a}-{b}",
                                "hora": x.creado_at})
        sanciones = []
        for x in win:
            if x.tipo in ("tarjeta_amarilla", "tarjeta_roja", "sancion", "descalificacion"):
                if x.tipo == "tarjeta_amarilla":
                    lab = "Amarilla"
                elif x.tipo == "tarjeta_roja":
                    lab = "Roja"
                elif x.tipo == "descalificacion":
                    lab = "Descalificación"
                else:
                    lab = str((x.extra or {}).get("tipo", "sancion")).capitalize()
                jug = _v_apellido(atl_nom.get(x.atleta_id or "", "")) if x.atleta_id else "—"
                sanciones.append({"jugador": jug, "lado": x.lado or "",
                                  "tipo": lab, "razon": x.razon or ""})
        ini_t = min((x.creado_at for x in win if x.creado_at), default=None)
        fin_t = max((x.creado_at for x in win if x.creado_at), default=None)
        bloques.append({"num": num, "local": sl, "visit": sv, "rallys": rallys,
                        "tiempos": tiempos, "sanciones": sanciones,
                        "inicio": ini_t, "fin": fin_t})

    sets_pts = {s.numero_set: (s.pts_local, s.pts_visitante) for s in sets}
    if not bloques and sets:
        # Sin bitácora en vivo (resultado cargado manual): un bloque por set
        # archivado con marcador real y secciones vacías, como la referencia.
        for s in sets:
            bloques.append({"num": s.numero_set, "local": s.pts_local,
                            "visit": s.pts_visitante, "rallys": [],
                            "tiempos": [], "sanciones": [],
                            "inicio": None, "fin": None})
    tot_l = sum(v[0] for v in sets_pts.values())
    tot_v = sum(v[1] for v in sets_pts.values())
    gan_l = sum(1 for s in sets if s.ganador_id and s.ganador_id == partido.equipo_local_id)
    gan_v = sum(1 for s in sets if s.ganador_id and s.ganador_id == partido.equipo_visit_id)

    async def _nombre(uid):
        if not uid:
            return ""
        r1 = await db.execute(select(Profile).where(Profile.id == uid))
        p = r1.scalar_one_or_none()
        return (p.nombre_completo if p and p.nombre_completo else "") or ""

    oficiales = {"juez2": "", "anotador": ""}
    try:
        rj = await db.execute(select(TorneoJuez, Profile).join(
            Profile, Profile.id == TorneoJuez.user_id))
        for tj, pf in rj.all():
            rol = getattr(tj, "rol", None)
            if rol in oficiales and not oficiales[rol]:
                oficiales[rol] = pf.nombre_completo if pf else ""
    except Exception:
        pass
    arb1 = await _nombre(partido.arbitro_id)

    def _cap(eid):
        lst = ats.get(eid or "", [])
        cap = next((a for a in lst if (a["posicion"] or "").lower() == "capitan"), None)
        return _v_apellido((cap or (lst[0] if lst else {})).get("nombre", "")) if lst else "—"

    ini_p = getattr(partido, "iniciado_en", None)
    fin_p = getattr(partido, "finalizado_en", None)
    h_ini = _v_hora(ini_p or partido.fecha_hora)
    h_fin = _v_hora(fin_p or partido.fecha_hora)
    return {
        "titulo": f"{tor_nom} / {cat_nom}",
        "fecha": _v_fecha(ini_p or partido.fecha_hora),
        "rango": (h_ini, h_fin),
        "dur": _v_dur(ini_p, fin_p),
        "eq1": nombres.get(partido.equipo_local_id, "Por definir"),
        "eq2": nombres.get(partido.equipo_visit_id, "Por definir"),
        "sets_pts": sets_pts, "tot_l": tot_l, "tot_v": tot_v,
        "gan_l": gan_l, "gan_v": gan_v,
        "jug1": [{"num": i + 1, "nombre": _v_apellido(a["nombre"])} for i, a in enumerate(ats.get(partido.equipo_local_id or "", [])[:4])],
        "jug2": [{"num": i + 1, "nombre": _v_apellido(a["nombre"])} for i, a in enumerate(ats.get(partido.equipo_visit_id or "", [])[:4])],
        "bloques": bloques,
        "obs": getattr(partido, "observaciones", None) or "",
        "arb1": arb1, "arb2": oficiales["juez2"], "anot": oficiales["anotador"],
        "cap1": _cap(partido.equipo_local_id), "cap2": _cap(partido.equipo_visit_id),
        "fase": partido.fase, "cancha": partido.cancha or "—", "estado": partido.estado,
    }


def _v_flecha(c, x, ymid, w=14):
    """Flecha vectorial -> (las fuentes base no traen el glifo)."""
    c.setStrokeColor(_V_NEGRO)
    c.setLineWidth(0.9)
    c.line(x, ymid, x + w, ymid)
    c.line(x + w, ymid, x + w - 4, ymid + 2.2)
    c.line(x + w, ymid, x + w - 4, ymid - 2.2)


def _v_rango(c, cx, y, h, izq, der, tam=9, negrita=False):
    """Texto centrado 'izq -> der' con flecha dibujada."""
    f = "Helvetica-Bold" if negrita else "Helvetica"
    from reportlab.pdfbase.pdfmetrics import stringWidth
    w1, w2 = stringWidth(izq, f, tam), stringWidth(der, f, tam)
    aw, gap = 14, 5
    x0 = cx - (w1 + gap + aw + gap + w2) / 2
    c.setFillColor(_V_NEGRO)
    c.setFont(f, tam)
    base = _v_y(y + h) + (h - tam) / 2 + 1
    c.drawString(x0, base, izq)
    _v_flecha(c, x0 + w1 + gap, base + tam * 0.32, aw)
    c.drawString(x0 + w1 + gap + aw + gap, base, der)


def _v_rango_set(c, x, y, w, h, izq, der, dur):
    """Banda de set: 'H1 -> H2  DUR' centrado como grupo."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    f, tam = "Helvetica", 9
    w1, w2, wd = stringWidth(izq, f, tam), stringWidth(der, f, tam), stringWidth(dur, f, tam)
    aw, gap = 14, 5
    total = w1 + gap + aw + gap + w2 + gap * 2 + wd
    x0 = x + (w - total) / 2
    base = _v_y(y + h) + (h - tam) / 2 + 1
    c.setFillColor(_V_NEGRO)
    c.setFont(f, tam)
    c.drawString(x0, base, izq)
    _v_flecha(c, x0 + w1 + gap, base + tam * 0.32, aw)
    c.drawString(x0 + w1 + gap + aw + gap, base, der)
    c.drawString(x0 + w1 + gap + aw + gap + w2 + gap * 2, base, dur)


def _v_marco(c, x, y, w, h):
    for dx in (0, 1, 2.5):
        c.setStrokeColor(_V_LINEA)
        c.setLineWidth(0.75)
        c.rect(x + dx, _v_y(y + h) + dx, w - 2 * dx, h - 2 * dx, stroke=1, fill=0)


def _v_celda(c, x, y, w, h, texto="", tam=9, negrita=False, color=_V_NEGRO,
             fondo=None, centro=True, borde=True):
    yy = _v_y(y + h)
    if fondo is not None:
        c.setFillColor(fondo)
        c.rect(x, yy, w, h, stroke=0, fill=1)
    if borde:
        c.setStrokeColor(_V_LINEA)
        c.setLineWidth(0.75)
        c.rect(x, yy, w, h, stroke=1, fill=0)
    if texto:
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if negrita else "Helvetica", tam)
        if centro:
            c.drawCentredString(x + w / 2, yy + (h - tam) / 2 + 1, str(texto))
        else:
            c.drawString(x + 4, yy + (h - tam) / 2 + 1, str(texto))


def _v_pie(c):
    c.setFillColor(_V_NEGRO)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(696, _v_y(574.6) - 6, "Powered by Volleyball Referee")


def _v_encabezado(c, d):
    _v_marco(c, 25.4, 3.6, 791.6, 67)
    _v_celda(c, 32.6, 10.9, 311.3, 18, d["titulo"], 10, True, centro=False)
    _v_celda(c, 343.1, 10.9, 156, 18, d["fecha"], 9)
    _v_celda(c, 498.4, 10.9, 156, 18, "", 9)
    _v_rango(c, 498.4 + 78, 10.9, 18, d["rango"][0], d["rango"][1], 9)
    _v_celda(c, 653.6, 10.9, 63, 18, d["dur"], 9, True)
    filas = [(d["eq1"], d["sets_pts"], d["tot_l"], d["gan_l"], _V_ROJO),
             (d["eq2"], d["sets_pts"], d["tot_v"], d["gan_v"], _V_NEGRO)]
    for i, (nom, sp, tot, gan, marca) in enumerate(filas):
        y = 29.6 + i * 16.5
        _v_celda(c, 32.6, y, 311.3, 15.8, nom, 10, True, centro=False)
        c.setFillColor(marca)
        c.rect(336.5, _v_y(y + 15.8) + 5.5, 5, 5, stroke=0, fill=1)
        lado = 0 if i == 0 else 1
        s1 = sp.get(1, (None, None))[lado]
        s2 = sp.get(2, (None, None))[lado]
        s3 = sp.get(3, (None, None))[lado]
        vals = [s1, s2, s3, tot if tot else "", gan if (gan or tot) else ""]
        xs = [343.1, 382.9, 422.7, 462.5, 502.3]
        for j, v in enumerate(vals):
            _v_celda(c, xs[j], y, 39.8, 15.8, "" if v is None else v, 10, True)


def _v_jugadores(c, d):
    _v_marco(c, 25.4, 73.4, 791.6, 48.3)
    c.setFillColor(_V_NEGRO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(35.5, _v_y(81.5) - 7, "Jugadores")
    for k, (lst, xs) in enumerate((("jug1", [34.5, 207]), ("jug2", [465.7, 638.2]))):
        for j, bx in enumerate(xs):
            if j >= len(d[lst]):
                continue
            jg = d[lst][j]
            _v_celda(c, bx, 96.8, 21, 15, str(jg["num"]), 9, True,
                     colors.white if k else _V_NEGRO,
                     _V_NEGRO if k else None)
            c.setFillColor(_V_NEGRO)
            c.setFont("Helvetica", 9)
            c.drawString(bx + 25, _v_y(96.8 + 15) + 3, jg["nombre"])


def _v_rejilla(c, rallys, x, y, por_linea=32):
    """Rejilla serpentina: cada rally una celdilla coloreada por equipo ganador."""
    cw, chh, pitch, desf = 21, 15, 24, 7.5
    h_linea = chh + desf + 3
    yy = y
    for ini in range(0, len(rallys) or 1, por_linea):
        trozo = rallys[ini:ini + por_linea] if rallys else []
        for k, lado in enumerate(trozo):
            cx = x + k * pitch
            cy = yy + (desf if k % 2 else 0)
            fill = _V_ROJO if lado == "local" else _V_NEGRO
            c.setFillColor(fill)
            c.rect(cx, _v_y(cy + chh), cw, chh, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(cx + cw / 2, _v_y(cy + chh) + 4, str(ini + k + 1))
        yy += h_linea
    return yy - y


def _v_bloque_set(c, d, b, y_top):
    y = y_top
    _v_celda(c, 32.6, y + 7, 99.8, 31.3, f"Set {b['num']}", 14, True, colors.white, _V_NEGRO)
    _v_celda(c, 131.6, y + 7, 33, 15.3, b["local"], 20, True)
    _v_celda(c, 131.6, y + 23, 33, 15.3, b["visit"], 20, True)
    _v_celda(c, 214.9, y + 7, 188.2, 18, "", 9)
    if b["inicio"] is None:
        c.setFillColor(_V_NEGRO)
        c.setFont("Helvetica", 9)
        c.drawCentredString(214.9 + 94.1, _v_y(y + 25) + 5, "Sin registro de horario")
    else:
        dur = _v_dur(b["inicio"], b["fin"])
        _v_rango_set(c, 214.9, y + 7, 188.2, 18, _v_hora(b["inicio"]), _v_hora(b["fin"]), dur)
    y += 46
    # marco del bloque (se dibuja al final con la altura real)
    y0_marco = y_top - 7
    c.setFillColor(_V_NEGRO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(35.5, _v_y(y) - 10, "Sanciones")
    y += 14
    if b["sanciones"]:
        _v_celda(c, 32.6, y, 170, 14, "Jugador", 8, True, colors.white, _V_NEGRO)
        _v_celda(c, 202.6, y, 110, 14, "Equipo", 8, True, colors.white, _V_NEGRO)
        _v_celda(c, 312.6, y, 140, 14, "Tipo", 8, True, colors.white, _V_NEGRO)
        y += 14
        for s in b["sanciones"]:
            eq = d["eq1"] if s["lado"] == "local" else (d["eq2"] if s["lado"] == "visitante" else "—")
            _v_celda(c, 32.6, y, 170, 14, s["jugador"], 9)
            _v_celda(c, 202.6, y, 110, 14, eq[:40], 9)
            _v_celda(c, 312.6, y, 140, 14, s["tipo"], 9)
            y += 14
    else:
        _v_celda(c, 32.6, y, 420, 15, "", 9)
        y += 15
    y += 8
    c.setFillColor(_V_NEGRO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(35.5, _v_y(y) - 10, "Tiempos muertos")
    y += 14
    for lado, nom, marca in (("local", d["eq1"], _V_ROJO), ("visitante", d["eq2"], _V_NEGRO)):
        tms = [t for t in b["tiempos"] if t["lado"] == lado]
        txt = f"{nom[:40]}: " + ("  ".join(f"TM({t['score']})" for t in tms) if tms else "—")
        _v_celda(c, 32.6 if lado == "local" else 417.6, y, 385, 16, txt, 9, centro=False)
    y += 16
    y += 8
    c.setFillColor(_V_NEGRO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(35.5, _v_y(y) - 10, "Puntos")
    y += 14
    if b["rallys"]:
        y += _v_rejilla(c, b["rallys"], 34.5, y)
    else:
        c.setFillColor(_V_NEGRO)
        c.setFont("Helvetica", 9)
        c.drawString(35.5, _v_y(y) - 10, "Sin puntos registrados.")
        y += 14
    _v_marco(c, 25.4, y0_marco, 791.6, (y - y0_marco) + 7)
    return y + 7


def _v_tarjeta_firma(c, x, y, w, etiqueta, nombre):
    _v_celda(c, x, y, 64.5, 15.8, etiqueta, 9, True, centro=False)
    _v_celda(c, x + 63.8, y, w - 63.8, 15.8, nombre or "", 9, centro=False)
    c.setStrokeColor(_V_LINEA)
    c.setLineWidth(0.75)
    c.rect(x + 63.8, _v_y(y + 66.8) , w - 63.8, 50, stroke=1, fill=0)


def _v_resumen(c, d):
    _v_marco(c, 26.4, 73, 789.6, 68.6)
    c.setFillColor(_V_NEGRO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(35.5, _v_y(80) - 7, "Observaciones")
    if d["obs"]:
        c.setFont("Helvetica", 9)
        c.drawString(36.3, _v_y(101.4) - 6, d["obs"][:160])
    _v_marco(c, 26.4, 146.4, 789.6, 176.6)
    c.setFillColor(_V_NEGRO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(35.5, _v_y(153.5) - 7, "Firmas")
    _v_tarjeta_firma(c, 32.6, 172.1, 222.8, "Árbitro 1", d["arb1"])
    _v_tarjeta_firma(c, 310.1, 172.1, 222, "Árbitro 2", d["arb2"])
    _v_tarjeta_firma(c, 586.9, 172.1, 222.7, "Anotador", d["anot"])
    _v_tarjeta_firma(c, 32.6, 248.6, 222.8, "Capitán", d["cap1"])
    _v_tarjeta_firma(c, 309.8, 248.6, 222.3, "Capitán", d["cap2"])


def _construir_pdf_voley(buf, d):
    from reportlab.pdfgen import canvas as _canvas
    c = _canvas.Canvas(buf, pagesize=(_V_PW, _V_PH))
    c.setTitle("Reporte de partido")
    bloques = d["bloques"] or [{"num": 1, "local": d["sets_pts"].get(1, ("—", "—"))[0],
                                "visit": d["sets_pts"].get(1, ("—", "—"))[1],
                                "rallys": [], "tiempos": [], "sanciones": [],
                                "inicio": None, "fin": None}]
    # Pág 1: encabezado + jugadores + set 1
    _v_encabezado(c, d)
    _v_jugadores(c, d)
    fin1 = _v_bloque_set(c, d, bloques[0], 124.3)
    _v_pie(c)
    c.showPage()
    # Pág 2+: sets restantes (2 por página)
    rest = bloques[1:]
    for i in range(0, len(rest), 2):
        yy = 7.7
        for b in rest[i:i + 2]:
            yy = _v_bloque_set(c, d, b, yy) + 5
        _v_pie(c)
        c.showPage()
    # Resumen
    _v_encabezado(c, d)
    _v_resumen(c, d)
    _v_pie(c)
    c.showPage()
    c.save()
