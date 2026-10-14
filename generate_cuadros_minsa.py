"""Genera los 4 cuadros del Trabajo MINSA según 'Especificaciones de los cuadros presupuestales'.

Todos los montos se leen de los .xls oficiales de Consulta Amigable consultados el 09/10/2026
08:48-09:01, es decir, información al cierre del 08/10/2026. Así los cuatro cuadros comparten
fecha de corte y cada número es trazable a su archivo de origen.
"""
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

CARPETA = Path(r"C:\semestre 2026-B\Contabilidad gerencial y tributacion")
DESTINO = CARPETA / "Cuadros_Presupuestales_MINSA_08_Octubre_v2.xlsx"
CORTE = "08/10/2026"

FUENTE_XLS = {
    "nacional": "29938147.xls",
    "niveles": "29718952.xls",
    "pliegos": "6496950.xls",
    "fuentes": "58516664.xls",
}

# ── Lectura de los .xls del portal ──────────────────────────────────────────────
def _num(texto: str) -> int:
    return int(texto.replace(",", "").strip())


def leer_xls(nombre: str) -> tuple[str, list[dict]]:
    """Devuelve (fecha de consulta, filas). Columnas del portal: PIA, PIM, Certificación,
    Compromiso Anual, [Ejecución] Atención de Compromiso Mensual, Devengado, Girado, Avance."""
    html = (CARPETA / nombre).read_text(encoding="latin1")
    fecha = re.search(r"Fecha de la Consulta:\s*([^<]+)", html).group(1).strip()
    tabla = re.search(r'<table[^>]*class=["\']Data["\'][^>]*>(.*?)</table>', html, re.S | re.I).group(1)
    filas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tabla, re.S | re.I):
        c = [re.sub(r"<[^>]+>", "", x).replace("&nbsp;", "").strip()
             for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if len(c) >= 8:
            filas.append({
                "desc": c[0], "pia": _num(c[1]), "pim": _num(c[2]),
                "compromiso": _num(c[5]),  # Atención de Compromiso Mensual (grupo "Ejecución")
                "devengado": _num(c[6]), "girado": _num(c[7]),
            })
    return fecha, filas


def por_prefijo(filas, prefijo):
    return next(f for f in filas if f["desc"].startswith(prefijo))


fechas = {}
fechas["nacional"], nac = leer_xls(FUENTE_XLS["nacional"])
fechas["niveles"], niv = leer_xls(FUENTE_XLS["niveles"])
fechas["pliegos"], pli = leer_xls(FUENTE_XLS["pliegos"])
fechas["fuentes"], fue = leer_xls(FUENTE_XLS["fuentes"])
assert len(set(fechas.values())) == 1, f"Los .xls no son de la misma consulta: {fechas}"

C1 = [("TOTAL NACIONAL", nac[0])]
C2 = [("Gobierno Nacional", por_prefijo(niv, "E:")),
      ("Gobierno Regional", por_prefijo(niv, "R:")),
      ("Gobierno Local", por_prefijo(niv, "M:"))]
C3 = [("011: M. DE SALUD", por_prefijo(pli, "011")),
      ("135: SEGURO INTEGRAL DE SALUD (SIS)", por_prefijo(pli, "135")),
      ("136: INST. NAC. ENFERMEDADES NEOPLASICAS - INEN", por_prefijo(pli, "136")),
      ("131: INSTITUTO NACIONAL DE SALUD (INS)", por_prefijo(pli, "131")),
      ("134: SUPERINTENDENCIA NACIONAL DE SALUD (SUSALUD)", por_prefijo(pli, "134"))]
C4 = [("Recursos Ordinarios", por_prefijo(fue, "1:")),
      ("Donaciones y Transferencias", por_prefijo(fue, "4:")),
      ("Recursos Directamente Recaudados", por_prefijo(fue, "2:")),
      ("Recursos por Operaciones Oficiales de Crédito", por_prefijo(fue, "3:")),
      ("Recursos Determinados", por_prefijo(fue, "5:"))]
assert len(pli) == 5 and len(fue) == 5 and len(niv) == 3, "El portal devolvió filas inesperadas"

# ── Estilos (una sola tipografía, 14 pt) ────────────────────────────────────────
FUENTE = "Calibri"
F_NORMAL = Font(name=FUENTE, size=14)
F_BOLD = Font(name=FUENTE, size=14, bold=True)
F_TITULO = Font(name=FUENTE, size=16, bold=True, color="1F3864")
F_HEADER = Font(name=FUENTE, size=14, bold=True, color="FFFFFF")
F_PIE = Font(name=FUENTE, size=14, italic=True, color="404040")
FILL_HEADER = PatternFill("solid", start_color="1F3864")
FILL_TOTAL = PatternFill("solid", start_color="D9E1F2")
FILL_SUAVE = PatternFill("solid", start_color="F2F2F2")
LINEA = Side(style="thin", color="8EA9DB")
BORDE = Border(left=LINEA, right=LINEA, top=LINEA, bottom=LINEA)
FMT_SOLES = "#,##0"
FMT_PCT = "0.0%"
IZQ = Alignment(horizontal="left", vertical="center", wrap_text=True)
DER = Alignment(horizontal="right", vertical="center")
CEN = Alignment(horizontal="center", vertical="center", wrap_text=True)

PIE_BASE = f"Fuente: MEF, Consulta Amigable. Información al {CORTE}."
PIE_AVANCE = "Avance = Devengado ÷ PIM."
NOTA_COMPROMISO = ("Compromiso = columna \"Atención de Compromiso Mensual\" del grupo Ejecución "
                   "del portal (no es el Compromiso Anual ni la Certificación).")


def encabezado(ws, col_h: str):
    for rango, texto in [("A3:A4", "Categoría"), ("B3:B4", "PIA"), ("C3:C4", "PIM"),
                         ("D3:F3", "Ejecución"), ("G3:G4", "Avance %"),
                         ("H3:H4", col_h), ("I3:I4", "Verificación")]:
        ws.merge_cells(rango)
        ws[rango.split(":")[0]] = texto
    for col, texto in zip("DEF", ["Compromiso", "Devengado", "Girado"]):
        ws[f"{col}4"] = texto
    for fila in (3, 4):
        for col in "ABCDEFGHI":
            celda = ws[f"{col}{fila}"]
            celda.font, celda.fill, celda.alignment, celda.border = F_HEADER, FILL_HEADER, CEN, BORDE
    ws.row_dimensions[3].height = 24
    ws.row_dimensions[4].height = 24


def fila_datos(ws, r: int, nombre: str, d: dict, col_h_formula: str, fmt_h: str, total=False):
    ws[f"A{r}"] = nombre
    for col, k in zip("BCDEF", ["pia", "pim", "compromiso", "devengado", "girado"]):
        ws[f"{col}{r}"] = d[k] if not total else d[k]
    ws[f"G{r}"] = f"=E{r}/C{r}"
    ws[f"H{r}"] = col_h_formula
    ws[f"I{r}"] = f'=IF(AND(D{r}>=E{r},E{r}>=F{r},E{r}<=C{r}),"OK","REVISAR")'
    estilo_fila(ws, r, fmt_h, total)


def estilo_fila(ws, r, fmt_h, total=False):
    for col in "ABCDEFGHI":
        c = ws[f"{col}{r}"]
        c.font = F_BOLD if total else F_NORMAL
        c.border = BORDE
        if total:
            c.fill = FILL_TOTAL
        if col == "A":
            c.alignment = IZQ
        elif col == "I":
            c.alignment = CEN
        else:
            c.alignment = DER
            c.number_format = FMT_PCT if col == "G" else (fmt_h if col == "H" else FMT_SOLES)


def anchos(ws, a=58):
    ws.column_dimensions["A"].width = a
    for col in "BCDEF":
        ws.column_dimensions[col].width = 22
    ws.column_dimensions["G"].width = 13
    ws.column_dimensions["H"].width = 22
    ws.column_dimensions["I"].width = 16


def pie(ws, r: int, lineas: list[str]):
    for i, texto in enumerate(lineas):
        ws.merge_cells(f"A{r + i}:I{r + i}")
        ws[f"A{r + i}"] = texto
        ws[f"A{r + i}"].font = F_PIE
        ws[f"A{r + i}"].alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws.row_dimensions[r + i].height = 22


def titulo(ws, texto):
    ws["A1"] = texto
    ws["A1"].font = F_TITULO


def con_etiquetas(chart, porcentaje=False, valor=False):
    chart.dataLabels = DataLabelList()
    chart.dataLabels.showPercent = porcentaje
    chart.dataLabels.showVal = valor
    chart.dataLabels.showSerName = False
    chart.dataLabels.showCatName = porcentaje
    chart.dataLabels.showLeaderLines = porcentaje
    return chart


def grafico_barras(titulo_, ws, cats, series, ancla, horizontal=False, pct=False):
    ch = BarChart()
    ch.type = "bar" if horizontal else "col"
    ch.title = titulo_
    ch.height, ch.width = 9, 18
    for ref in series:
        ch.add_data(ref, titles_from_data=True)
    ch.set_categories(cats)
    ch.y_axis.numFmt = FMT_PCT if pct else '#,##0,,," mil M"'
    ch.y_axis.majorGridlines = None
    ch.legend.position = "b"
    if pct:
        ch.legend = None
        con_etiquetas(ch, valor=True)
        ch.dataLabels.numFmt = FMT_PCT
    ws.add_chart(ch, ancla)


def grafico_circular(titulo_, ws, cats, datos, ancla):
    ch = PieChart()
    ch.title = titulo_
    ch.height, ch.width = 9, 14
    ch.add_data(datos, titles_from_data=False)
    ch.set_categories(cats)
    con_etiquetas(ch, porcentaje=True)
    ch.dataLabels.numFmt = FMT_PCT
    ch.legend.position = "b"
    ws.add_chart(ch, ancla)


def tabla_auxiliar(ws, r, filas):
    """Pequeña tabla para alimentar gráficos que necesitan agrupar valores."""
    ws[f"K{r}"] = "Datos para gráficos"
    ws[f"K{r}"].font = F_BOLD
    for i, (etq, formula) in enumerate(filas, start=1):
        ws[f"K{r + i}"], ws[f"L{r + i}"] = etq, formula
        ws[f"K{r + i}"].font = ws[f"L{r + i}"].font = F_NORMAL
        ws[f"L{r + i}"].number_format = FMT_SOLES
    ws.column_dimensions["K"].width = 24
    ws.column_dimensions["L"].width = 22


wb = Workbook()
wb.remove(wb.active)

# ── Cuadro 1 ────────────────────────────────────────────────────────────────────
ws1 = wb.create_sheet("Cuadro 1 - Presupuesto Nacional")
titulo(ws1, f"Cuadro 1: Presupuesto Nacional - Información MEF al {CORTE}")
encabezado(ws1, "Saldo por Ejecutar")
fila_datos(ws1, 5, C1[0][0], C1[0][1], "=C5-E5", FMT_SOLES)
pie(ws1, 7, [f"{PIE_BASE} {PIE_AVANCE}", NOTA_COMPROMISO])
# Contexto opcional de la sección 10: el sector Salud y el MINSA frente al total nacional.
ws1["A10"] = "Contexto: participación en el PIM nacional"
ws1["A10"].font = F_BOLD
for r, (etq, ref) in enumerate([("Sector Salud (TOTAL Cuadro 3)", "='Cuadro 3 - Sector Salud (MINSA)'!C10"),
                                ("Pliego 011: M. DE SALUD", "='Cuadro 3 - Sector Salud (MINSA)'!C5")], start=11):
    ws1[f"A{r}"], ws1[f"C{r}"], ws1[f"G{r}"] = etq, ref, f"=C{r}/C$5"
    for col in "ACG":
        ws1[f"{col}{r}"].font = F_NORMAL
    ws1[f"C{r}"].number_format, ws1[f"G{r}"].number_format = FMT_SOLES, FMT_PCT
    ws1[f"C{r}"].alignment = ws1[f"G{r}"].alignment = DER
ws1["B11"] = ws1["B12"] = "PIM:"
ws1["F11"] = ws1["F12"] = "% PIM nac.:"
for c in ("B11", "B12", "F11", "F12"):
    ws1[c].font, ws1[c].alignment = F_NORMAL, DER
anchos(ws1)
tabla_auxiliar(ws1, 15, [("PIA", "=B5"), ("PIM", "=C5"), ("Devengado", "=E5"),
                         ("Avance (devengado)", "=E5"), ("Saldo por ejecutar", "=H5")])
grafico_barras("Presupuesto nacional: PIA, PIM y devengado (S/)", ws1,
               Reference(ws1, min_col=11, min_row=16, max_row=18),
               [Reference(ws1, min_col=12, min_row=15, max_row=18)], "A15")
grafico_circular("Avance vs. saldo por ejecutar (% del PIM)", ws1,
                 Reference(ws1, min_col=11, min_row=19, max_row=20),
                 Reference(ws1, min_col=12, min_row=19, max_row=20), "E15")

# ── Cuadros 2, 3 y 4 (misma estructura) ─────────────────────────────────────────
def cuadro_con_total(nombre_hoja, texto_titulo, filas, etiqueta_total, pies):
    ws = wb.create_sheet(nombre_hoja)
    titulo(ws, texto_titulo)
    encabezado(ws, "% del PIM Total")
    r_total = 5 + len(filas)
    for i, (nombre, d) in enumerate(filas):
        r = 5 + i
        fila_datos(ws, r, nombre, d, f"=C{r}/C${r_total}", FMT_PCT)
    ws[f"A{r_total}"] = etiqueta_total
    for col in "BCDEF":
        ws[f"{col}{r_total}"] = f"=SUM({col}5:{col}{r_total - 1})"
    ws[f"G{r_total}"] = f"=E{r_total}/C{r_total}"
    ws[f"H{r_total}"] = f"=SUM(H5:H{r_total - 1})"
    ws[f"I{r_total}"] = (f'=IF(AND(D{r_total}>=E{r_total},E{r_total}>=F{r_total},'
                         f'E{r_total}<=C{r_total}),"OK","REVISAR")')
    estilo_fila(ws, r_total, FMT_PCT, total=True)
    pie(ws, r_total + 2, pies)
    anchos(ws)
    return ws, r_total


ws2, t2 = cuadro_con_total(
    "Cuadro 2 - Nivel de Gobierno",
    f"Cuadro 2: Presupuesto por Nivel de Gobierno - Información MEF al {CORTE}",
    C2, "TOTAL", [f"{PIE_BASE} {PIE_AVANCE}", NOTA_COMPROMISO])
grafico_barras("PIA, PIM y devengado por nivel de gobierno (S/)", ws2,
               Reference(ws2, min_col=1, min_row=5, max_row=7),
               [Reference(ws2, min_col=2, max_col=3, min_row=4, max_row=7),
                Reference(ws2, min_col=5, min_row=4, max_row=7)], "A13")
grafico_circular("Participación en el PIM total", ws2,
                 Reference(ws2, min_col=1, min_row=5, max_row=7),
                 Reference(ws2, min_col=3, min_row=5, max_row=7), "E13")

PIE_SALUD = f"{PIE_BASE} Sector Salud, pliegos del Gobierno Nacional. {PIE_AVANCE}"
ws3, t3 = cuadro_con_total(
    "Cuadro 3 - Sector Salud (MINSA)",
    f"Cuadro 3: Presupuesto del Sector Salud (Pliegos) - Información MEF al {CORTE}",
    C3, "TOTAL SECTOR SALUD",
    [PIE_SALUD,
     "Alcance: solo pliegos del Gobierno Nacional (sector 11). No incluye el gasto en salud de "
     "gobiernos regionales y locales.",
     NOTA_COMPROMISO])
ws3["A16"] = "El PIM del sector Salud representa del PIM nacional (Cuadro 1):"
ws3["G16"] = "=C10/'Cuadro 1 - Presupuesto Nacional'!C5"
ws3["A16"].font = ws3["G16"].font = F_BOLD
ws3["G16"].number_format, ws3["G16"].alignment = FMT_PCT, DER
ws3.merge_cells("A16:F16")
grafico_circular("Participación de cada pliego en el PIM del sector", ws3,
                 Reference(ws3, min_col=1, min_row=5, max_row=9),
                 Reference(ws3, min_col=3, min_row=5, max_row=9), "A18")
grafico_barras("Avance % por pliego", ws3,
               Reference(ws3, min_col=1, min_row=5, max_row=9),
               [Reference(ws3, min_col=7, min_row=4, max_row=9)], "E18", horizontal=True, pct=True)

ws4, t4 = cuadro_con_total(
    "Cuadro 4 - Fuentes Salud",
    f"Cuadro 4: Presupuesto del Sector Salud por Fuente de Financiamiento - Información MEF al {CORTE}",
    C4, "TOTAL",
    [PIE_SALUD,
     "Nota: el compromiso y el girado del TOTAL difieren en 1 sol del Cuadro 3 por redondeo del "
     "portal; no es un error de digitación.",
     NOTA_COMPROMISO])
tabla_auxiliar(ws4, 16, [("Recursos Ordinarios", "=C5"), ("Otras fuentes", "=SUM(C6:C9)")])
grafico_circular("Participación de cada fuente en el PIM", ws4,
                 Reference(ws4, min_col=11, min_row=17, max_row=18),
                 Reference(ws4, min_col=12, min_row=17, max_row=18), "A16")
grafico_barras("Avance % por fuente", ws4,
               Reference(ws4, min_col=1, min_row=5, max_row=9),
               [Reference(ws4, min_col=7, min_row=4, max_row=9)], "E16", pct=True)

# ── Datos de control y control cruzado ──────────────────────────────────────────
wc = wb.create_sheet("Datos de control", 0)
wc["A1"] = "Datos de control"
wc["A1"].font = F_TITULO
filtros = ("Año 2026; Incluye: Actividades y Proyectos. C1: total sin filtro. C2: por nivel de gobierno. "
           "C3: Nivel E (Gobierno Nacional) > Sector 11 Salud > Pliego. "
           "C4: Nivel E > Sector 11 Salud > Fuente de financiamiento.")
datos = [("Fecha de corte de la información", CORTE),
         ("Año fiscal", "2026"),
         ("Fuente", "MEF, Consulta Amigable (SIAF)"),
         ("Filtros usados en la consulta", filtros),
         ("Integrante que extrajo los datos", ""),
         ("Fecha en que se extrajeron", f"{fechas['pliegos']} (consulta de la mañana; el portal "
                                        f"muestra el cierre del día anterior)"),
         ("Archivos de origen", ", ".join(f"{k}: {v}" for k, v in FUENTE_XLS.items()))]
for i, (k, v) in enumerate(datos, start=3):
    wc[f"A{i}"], wc[f"B{i}"] = k, v
    wc[f"A{i}"].font, wc[f"B{i}"].font = F_BOLD, F_NORMAL
    wc[f"B{i}"].alignment = IZQ
    for col in "AB":
        wc[f"{col}{i}"].border = BORDE
    wc.row_dimensions[i].height = 60 if k.startswith(("Filtros", "Archivos", "Fecha en")) else 22
wc["B7"].fill = PatternFill("solid", start_color="FFF2CC")  # integrante: llenar a mano
wc.column_dimensions["A"].width = 40
wc.column_dimensions["B"].width = 110

wx = wb.create_sheet("Control cruzado")
wx["A1"] = "Control cruzado entre cuadros"
wx["A1"].font = F_TITULO
H1, H2, H3, H4 = ("'Cuadro 1 - Presupuesto Nacional'", "'Cuadro 2 - Nivel de Gobierno'",
                  "'Cuadro 3 - Sector Salud (MINSA)'", "'Cuadro 4 - Fuentes Salud'")


controles = [
    ("TOTAL del Cuadro 2 vs. fila del Cuadro 1 (PIA, PIM, compromiso, devengado, girado)",
     '=IF(AND(' + ",".join(f"{H2}!{c}8={H1}!{c}5" for c in "BCDEF") + '),"Sí","No")'),
    ("TOTAL del Cuadro 4 vs. TOTAL del Cuadro 3 (iguales; compromiso y girado ±1 sol)",
     '=IF(AND(' + ",".join(f"ABS({H4}!{c}10-{H3}!{c}10)<=1" for c in "BCDEF") + '),"Sí","No")'),
    ("PIM del Cuadro 3 menor que el PIM del Cuadro 1", f'=IF({H3}!C10<{H1}!C5,"Sí","No")'),
    ("Suma de % del PIM = 100.0 (cuadros 2, 3 y 4)",
     f'=IF(AND(ROUND({H2}!H8,3)=1,ROUND({H3}!H10,3)=1,ROUND({H4}!H10,3)=1),"Sí","No")'),
    ("Compromiso ≥ Devengado ≥ Girado y Devengado ≤ PIM en todas las filas",
     f'=IF(COUNTIF({H1}!I5:I5,"OK")+COUNTIF({H2}!I5:I8,"OK")+COUNTIF({H3}!I5:I10,"OK")'
     f'+COUNTIF({H4}!I5:I10,"OK")=17,"Sí","No")'),
]
wx["A3"], wx["B3"] = "Comparación", "Coincide"
for c in ("A3", "B3"):
    wx[c].font, wx[c].fill, wx[c].alignment, wx[c].border = F_HEADER, FILL_HEADER, CEN, BORDE
for i, (texto, formula) in enumerate(controles, start=4):
    wx[f"A{i}"], wx[f"B{i}"] = texto, formula
    wx[f"A{i}"].font, wx[f"B{i}"].font = F_NORMAL, F_BOLD
    wx[f"A{i}"].alignment, wx[f"B{i}"].alignment = IZQ, CEN
    wx[f"A{i}"].border = wx[f"B{i}"].border = BORDE
    wx.row_dimensions[i].height = 40
r = 4 + len(controles) + 1
for j, (etq, f) in enumerate([("PIM sector Salud / PIM nacional", f"={H3}!C10/{H1}!C5"),
                              ("PIM pliego MINSA / PIM nacional", f"={H3}!C5/{H1}!C5")]):
    wx[f"A{r + j}"], wx[f"B{r + j}"] = etq, f
    wx[f"A{r + j}"].font = wx[f"B{r + j}"].font = F_NORMAL
    wx[f"B{r + j}"].number_format, wx[f"B{r + j}"].alignment = FMT_PCT, CEN
wx.column_dimensions["A"].width = 95
wx.column_dimensions["B"].width = 16

for ws in wb.worksheets:
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1

wb.save(DESTINO)
print(f"Guardado: {DESTINO}")
print(f"Fecha de consulta común a los 4 .xls: {fechas['nacional']}")
