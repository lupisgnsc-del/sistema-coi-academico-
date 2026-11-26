"""Exportación a Excel (con fórmulas vivas) y PDF."""
import io
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT = "Arial"
MONEY = '#,##0.00;(#,##0.00);"-"'
HDR_FILL = PatternFill("solid", fgColor="1F3A5F")
TOT_FILL = PatternFill("solid", fgColor="E8EEF5")
THIN = Side(style="thin", color="999999")


def limpio(v):
    """Evita inyección de fórmulas en texto escrito por el usuario."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return " " + v
    return v


def _d(iso):
    y, m, d = map(int, iso.split("-"))
    return date(y, m, d)


def _hdr(ws, row, headers):
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = Font(name=FONT, bold=True, color="FFFFFF")
        c.fill = HDR_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _font_all(wb):
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.font.name != FONT:
                    f = c.font
                    c.font = Font(name=FONT, bold=f.bold, italic=f.italic,
                                  color=f.color, size=f.size or 10)


def excel_completo(empresa, desde, hasta, cuentas, movs):
    """cuentas: filas de balanza (dict). movs: movimientos hasta 'hasta'."""
    wb = Workbook()

    # ---------- Parámetros ----------
    p = wb.active
    p.title = "Parametros"
    p["A1"] = limpio(f"{empresa['nombre']}  ·  RFC: {empresa['rfc'] or 'N/D'}")
    p["A1"].font = Font(name=FONT, bold=True, size=14)
    p["A3"], p["A4"] = "Fecha inicial del periodo", "Fecha final del periodo"
    p["B3"], p["B4"] = _d(desde), _d(hasta)
    for ref in ("B3", "B4"):
        p[ref].number_format = "dd/mm/yyyy"
        p[ref].font = Font(name=FONT, color="0000FF", bold=True)
        p[ref].fill = PatternFill("solid", fgColor="FFFF00")
    p["A6"] = "Leyenda: celdas amarillas/azules = datos que puedes editar; el resto son fórmulas."
    p["A7"] = ("Cambia las fechas y la Balanza, el Estado de resultados y el Balance "
               "se recalculan solos desde la hoja Movimientos.")
    p["A8"] = ("Los saldos iniciales base (hoja Balanza, columna E) son datos capturados; "
               "los estados financieros son acumulados a la fecha final.")
    _widths(p, [38, 16])

    # ---------- Movimientos ----------
    mv = wb.create_sheet("Movimientos")
    _hdr(mv, 1, ["Póliza", "Fecha", "Cuenta", "Concepto", "Debe", "Haber"])
    for i, m in enumerate(movs, 2):
        mv.cell(i, 1, f'{m["tipo"][0]}-{m["numero"]}')
        c = mv.cell(i, 2, _d(m["fecha"]))
        c.number_format = "dd/mm/yyyy"
        mv.cell(i, 3, m["codigo"])
        mv.cell(i, 4, limpio(m["concepto"] or m["pconcepto"]))
        for col, key in ((5, "debe"), (6, "haber")):
            c = mv.cell(i, col, m[key])
            c.number_format = MONEY
            c.font = Font(name=FONT, color="0000FF")
    n = len(movs) + 1                      # última fila de datos
    last = max(n, 2)
    t = n + 2
    mv.cell(t, 4, "Totales").font = Font(name=FONT, bold=True)
    mv.cell(t, 5, f"=SUM(E2:E{last})")
    mv.cell(t, 6, f"=SUM(F2:F{last})")
    mv.cell(t + 1, 4, "Diferencia (debe − haber)")
    mv.cell(t + 1, 5, f"=E{t}-F{t}")
    for r in (t, t + 1):
        for col in (5, 6):
            mv.cell(r, col).number_format = MONEY
            mv.cell(r, col).fill = TOT_FILL
    mv.freeze_panes = "A2"
    _widths(mv, [12, 12, 14, 44, 16, 16])

    # ---------- Catálogo ----------
    ct = wb.create_sheet("Catalogo")
    _hdr(ct, 1, ["Código", "Cuenta", "Naturaleza", "Tipo", "Código agrupador SAT"])
    for i, c in enumerate(cuentas, 2):
        for j, v in enumerate([c["codigo"], c["nombre"], "Deudora" if c["naturaleza"] == "D" else "Acreedora",
                               c["tipo"], c["agrupador"]], 1):
            ct.cell(i, j, limpio(v))
    ct.freeze_panes = "A2"
    _widths(ct, [14, 40, 14, 12, 20])

    # ---------- Balanza ----------
    b = wb.create_sheet("Balanza")
    b["A1"] = limpio(f"Balanza de comprobación — {empresa['nombre']}")
    b["A1"].font = Font(name=FONT, bold=True, size=13)
    b["A2"], b["C2"] = "Periodo:", "al"
    b["B2"], b["D2"] = "=Parametros!B3", "=Parametros!B4"
    b["B2"].number_format = b["D2"].number_format = "dd/mm/yyyy"
    _hdr(b, 4, ["Código", "Cuenta", "Naturaleza", "Tipo", "Saldo inicial base",
                "Saldo inicial del periodo", "Cargos", "Abonos", "Saldo final"])
    r0 = 5
    rng = lambda col: f"Movimientos!${col}$2:${col}${last}"
    for i, c in enumerate(cuentas):
        r = r0 + i
        b.cell(r, 1, c["codigo"])
        b.cell(r, 2, limpio(c["nombre"]))
        b.cell(r, 3, c["naturaleza"])
        b.cell(r, 4, c["tipo"])
        e = b.cell(r, 5, c["base"])
        e.font = Font(name=FONT, color="0000FF")
        sgn = f'IF($C{r}="D",1,-1)'
        b.cell(r, 6, (f'=E{r}+{sgn}*(SUMIFS({rng("E")},{rng("C")},$A{r},{rng("B")},"<"&Parametros!$B$3)'
                      f'-SUMIFS({rng("F")},{rng("C")},$A{r},{rng("B")},"<"&Parametros!$B$3))'))
        for col, mc in ((7, "E"), (8, "F")):
            b.cell(r, col, (f'=SUMIFS({rng(mc)},{rng("C")},$A{r},{rng("B")},">="&Parametros!$B$3,'
                            f'{rng("B")},"<="&Parametros!$B$4)'))
        b.cell(r, 9, f"=F{r}+{sgn}*(G{r}-H{r})")
        for col in range(5, 10):
            b.cell(r, col).number_format = MONEY
    rl = r0 + len(cuentas) - 1
    rt = rl + 2
    b.cell(rt, 2, "Totales").font = Font(name=FONT, bold=True)
    for col in (7, 8):
        L = get_column_letter(col)
        b.cell(rt, col, f"=SUM({L}{r0}:{L}{rl})")
    b.cell(rt + 1, 2, "Diferencia cargos − abonos (debe ser 0)")
    b.cell(rt + 1, 7, f"=G{rt}-H{rt}")
    for r in (rt, rt + 1):
        for col in range(2, 10):
            b.cell(r, col).fill = TOT_FILL
        for col in (7, 8):
            b.cell(r, col).number_format = MONEY
    b.freeze_panes = "C5"
    _widths(b, [14, 38, 11, 11, 18, 20, 16, 16, 16])

    # ---------- Estado de resultados ----------
    er = wb.create_sheet("EstadoResultados")
    er["A1"] = limpio(f"Estado de resultados — {empresa['nombre']}")
    er["A1"].font = Font(name=FONT, bold=True, size=13)
    er["A2"], er["B2"] = "Acumulado al", "=Parametros!B4"
    er["B2"].number_format = "dd/mm/yyyy"
    tipo_r, saldo_r = f"Balanza!$D${r0}:$D${rl}", f"Balanza!$I${r0}:$I${rl}"
    filas = [(4, "Ingresos", f'=SUMIFS({saldo_r},{tipo_r},"Ingresos")'),
             (5, "(-) Costos", f'=SUMIFS({saldo_r},{tipo_r},"Costos")'),
             (6, "Utilidad bruta", "=B4-B5"),
             (7, "(-) Gastos", f'=SUMIFS({saldo_r},{tipo_r},"Gastos")'),
             (8, "Utilidad (pérdida) neta", "=B6-B7")]
    for r, lab, f in filas:
        er.cell(r, 1, lab)
        er.cell(r, 2, f).number_format = MONEY
    for r in (6, 8):
        for col in (1, 2):
            er.cell(r, col).font = Font(name=FONT, bold=True)
            er.cell(r, col).fill = TOT_FILL
    _widths(er, [32, 18])

    # ---------- Balance general ----------
    bg = wb.create_sheet("BalanceGeneral")
    bg["A1"] = limpio(f"Balance general — {empresa['nombre']}")
    bg["A1"].font = Font(name=FONT, bold=True, size=13)
    bg["A2"], bg["B2"] = "Al", "=Parametros!B4"
    bg["B2"].number_format = "dd/mm/yyyy"
    filas = [(4, "Activo", f'=SUMIFS({saldo_r},{tipo_r},"Activo")'),
             (6, "Pasivo", f'=SUMIFS({saldo_r},{tipo_r},"Pasivo")'),
             (7, "Capital contable", f'=SUMIFS({saldo_r},{tipo_r},"Capital")'),
             (8, "Resultado del ejercicio", "=EstadoResultados!B8"),
             (9, "Total pasivo + capital", "=B6+B7+B8"),
             (11, "Diferencia Activo − (Pasivo + Capital)", "=B4-B9")]
    for r, lab, f in filas:
        bg.cell(r, 1, lab)
        bg.cell(r, 2, f).number_format = MONEY
    for r in (4, 9, 11):
        for col in (1, 2):
            bg.cell(r, col).font = Font(name=FONT, bold=True)
            bg.cell(r, col).fill = TOT_FILL
    _widths(bg, [40, 18])

    _font_all(wb)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ----------------------------- PDF -----------------------------
def money(x):
    return f"{x:,.2f}"


def pdf_tabla(titulo, empresa, subtitulo, headers, rows, num_cols=(), bold_rows=(), widths=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title=titulo)
    st = getSampleStyleSheet()
    elems = [Paragraph(f"<b>{_esc(empresa['nombre'])}</b>  ·  RFC: {_esc(empresa['rfc'] or 'N/D')}", st["Title"]),
             Paragraph(f"<b>{_esc(titulo)}</b>", st["Heading2"]),
             Paragraph(_esc(subtitulo), st["Normal"]), Spacer(1, 0.4 * cm)]
    cell = st["BodyText"].clone("cell", fontSize=8, leading=10)
    data = [headers] + [[Paragraph(_esc(str(c)), cell) if i not in num_cols else str(c)
                         for i, c in enumerate(r)] for r in rows]
    t = Table(data, repeatRows=1, colWidths=widths)
    style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("FONTSIZE", (0, 0), (-1, -1), 8),
             ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    for ci in num_cols:
        style.append(("ALIGN", (ci, 0), (ci, -1), "RIGHT"))
    for ri in bold_rows:
        style += [("FONTNAME", (0, ri + 1), (-1, ri + 1), "Helvetica-Bold"),
                  ("BACKGROUND", (0, ri + 1), (-1, ri + 1), colors.HexColor("#E8EEF5"))]
    t.setStyle(TableStyle(style))
    elems.append(t)

    def pie(canvas, d):
        canvas.setFont("Helvetica", 7)
        canvas.drawString(1.5 * cm, 0.8 * cm, "Generado con COI Académico (uso educativo) — " + date.today().isoformat())
        canvas.drawRightString(landscape(A4)[0] - 1.5 * cm, 0.8 * cm, f"Página {d.page}")

    doc.build(elems, onFirstPage=pie, onLaterPages=pie)
    buf.seek(0)
    return buf


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
