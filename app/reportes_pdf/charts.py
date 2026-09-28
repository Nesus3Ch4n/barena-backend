"""Gráficas vectoriales simples para reportes (sin dependencias pesadas)."""
from reportlab.graphics.shapes import Drawing, String, Line, Rect, Polygon
from reportlab.lib.colors import HexColor

COLORES = [HexColor("#e07856"), HexColor("#0e8da0"), HexColor("#c9a227"),
           HexColor("#3d9b86"), HexColor("#c0392b"), HexColor("#7a6ff0")]
GRIS = HexColor("#98a4a6")
INK = HexColor("#0a2a35")


def _fmt(n):
    return str(int(n)) if float(n) == int(float(n)) else f"{float(n):.1f}"


def barras(datos, w=460, h=130):
    """datos: [(etiqueta, valor)]"""
    d = Drawing(w, h)
    if not datos:
        return d
    maxv = max(1, max(v for _, v in datos))
    pad_b, pad_t = 20, 12
    n = len(datos)
    slot = (w - 10) / n
    bw = min(40, slot - 10)
    for i, (et, v) in enumerate(datos):
        bh = max(2, ((h - pad_b - pad_t) * v) / maxv)
        x = 5 + i * slot + (slot - bw) / 2
        y = h - pad_b - bh
        d.add(Rect(x, y, bw, bh, fillColor=COLORES[i % len(COLORES)], strokeColor=None))
        t = String(x + bw / 2, y - 4, _fmt(v), fontSize=8, fontName="Helvetica-Bold",
                   fillColor=INK, textAnchor="middle")
        d.add(t)
        lab = String(x + bw / 2, h - 10, str(et)[:14], fontSize=7, fontName="Helvetica",
                     fillColor=GRIS, textAnchor="middle")
        d.add(lab)
    return d


def dona(datos, w=460, h=140):
    """datos: [(etiqueta, valor)]"""
    from math import cos, sin, pi
    d = Drawing(w, h)
    total = sum(v for _, v in datos) or 1
    cx, cy, r = 80, h / 2, 52
    ang = -pi / 2
    for i, (et, v) in enumerate(datos):
        if v <= 0:
            continue
        a0 = ang
        ang += (v / total) * 2 * pi
        pasos = max(2, int(24 * (ang - a0) / (2 * pi)) + 1)
        pts = [cx, cy]
        for k in range(pasos + 1):
            a = a0 + (ang - a0) * k / pasos
            pts += [cx + r * cos(a), cy + r * sin(a)]
        d.add(Polygon(pts, fillColor=COLORES[i % len(COLORES)], strokeColor=None))
    d.add(String(cx, cy + 5, str(total), fontSize=16, fontName="Helvetica-Bold",
                 fillColor=INK, textAnchor="middle"))
    y = 18
    for i, (et, v) in enumerate(datos):
        pct = round(100 * v / total)
        d.add(Rect(150, y - 8, 9, 9, fillColor=COLORES[i % len(COLORES)], strokeColor=None))
        d.add(String(163, y, f"{et}: {v} ({pct}%)", fontSize=8, fontName="Helvetica", fillColor=INK))
        y += 16
    return d


def lineas(series, w=460, h=130):
    """series: [(etiqueta, [valores])]"""
    d = Drawing(w, h)
    vals = [v for _, vs in series for v in vs]
    if not vals:
        return d
    maxv = max(1, max(vals))
    pad_l, pad_b, pad_t = 28, 20, 10
    n = max(1, max(len(vs) for _, vs in series))
    px = lambda i: pad_l + (i * (w - pad_l - 10)) / max(1, n - 1)
    py = lambda v: h - pad_b - ((h - pad_b - pad_t) * v) / maxv
    for f in (0, 0.5, 1):
        y = py(maxv * f)
        d.add(Line(pad_l, y, w - 10, y, strokeColor=HexColor("#e5ebe9")))
        d.add(String(4, y + 3, str(round(maxv * f)), fontSize=7, fontName="Helvetica", fillColor=GRIS))
    for si, (et, vs) in enumerate(series):
        col = COLORES[si % len(COLORES)]
        for i in range(len(vs) - 1):
            d.add(Line(px(i), py(vs[i]), px(i + 1), py(vs[i + 1]), strokeColor=col, strokeWidth=2))
    return d
