"""Cliente directo para el portal web de Consulta Amigable del MEF (SIAF).

Permite extraer datos de ejecución presupuestal en tiempo real por:
- Año (y)
- Nivel de gobierno (E: Nacional, R: Regional, M: Local)
- Sector / Ministerio (ej. 11: SALUD, 10: EDUCACION, 36: TRANSPORTES, etc.)
- Pliego institucional
- Mes de ejecución (1 a 12: Enero a Diciembre)

Soporta exportación directa a Excel (.xlsx) y estructuración en JSON/DataFrames.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from . import core

BASE_URL_MENSUAL = "https://apps5.mineco.gob.pe/transparencia/mensual/Navegar_6.aspx"
BASE_URL_DIARIA = "https://apps5.mineco.gob.pe/transparencia/Navegador/Navegar_7.aspx"
BASE_URL = BASE_URL_MENSUAL
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Mapeo de ministerios / sectores comunes del Gobierno Nacional
SECTORES_GOBIERNO_NACIONAL: dict[str, str] = {
    "01": "PRESIDENCIA CONSEJO MINISTROS",
    "03": "CULTURA",
    "04": "PODER JUDICIAL",
    "05": "AMBIENTAL",
    "06": "JUSTICIA",
    "07": "INTERIOR",
    "08": "RELACIONES EXTERIORES",
    "09": "ECONOMIA Y FINANZAS",
    "10": "EDUCACION",
    "11": "SALUD",
    "12": "TRABAJO Y PROMOCION DEL EMPLEO",
    "13": "AGRARIO Y DE RIEGO",
    "16": "ENERGIA Y MINAS",
    "19": "CONTRALORIA GENERAL",
    "20": "DEFENSORIA DEL PUEBLO",
    "21": "JUNTA NACIONAL DE JUSTICIA",
    "22": "MINISTERIO PUBLICO",
    "24": "TRIBUNAL CONSTITUCIONAL",
    "26": "DEFENSA",
    "27": "FUERO MILITAR POLICIAL",
    "28": "CONGRESO DE LA REPUBLICA",
    "31": "JURADO NACIONAL DE ELECCIONES",
    "32": "OFICINA NACIONAL DE PROCESOS ELECTORALES",
    "33": "REGISTRO NACIONAL DE IDENTIFICACION Y ESTADO CIVIL",
    "35": "COMERCIO EXTERIOR Y TURISMO",
    "36": "TRANSPORTES Y COMUNICACIONES",
    "37": "VIVIENDA CONSTRUCCION Y SANEAMIENTO",
    "38": "PRODUCCION",
    "39": "MUJER Y POBLACIONES VULNERABLES",
    "40": "DESARROLLO E INCLUSION SOCIAL",
}

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"
]


def normalizar_texto(texto: str) -> str:
    texto = texto.upper()
    reemplazos = (("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"), ("Ü", "U"), ("Ñ", "N"))
    for a, b in reemplazos:
        texto = texto.replace(a, b)
    return texto.strip()


def resolver_sector(ministerio_o_codigo: str) -> tuple[str, str]:
    """Resuelve un nombre o código de ministerio al código de sector (2 dígitos) y nombre canónico."""
    query = normalizar_texto(ministerio_o_codigo)
    if not query:
        return "", ""

    # Si pasaron código numérico directo
    if query.isdigit():
        cod = query.zfill(2)
        nombre = SECTORES_GOBIERNO_NACIONAL.get(cod, f"SECTOR {cod}")
        return cod, nombre

    # Búsqueda por palabras clave en los sectores
    for cod, nombre in SECTORES_GOBIERNO_NACIONAL.items():
        if query == cod or query in normalizar_texto(nombre):
            return cod, nombre

    # Alias comunes
    alias = {
        "PCM": "01",
        "MINCUL": "03",
        "PJ": "04",
        "MINAM": "05",
        "MINJUS": "06",
        "MININTER": "07",
        "RREE": "08",
        "MEF": "09",
        "MINEDU": "10",
        "MINSA": "11",
        "MTPE": "12",
        "MIDAGRI": "13",
        "AGRICULTURA": "13",
        "MTC": "36",
        "MINDEF": "26",
        "MINEM": "16",
        "VIVIENDA": "37",
        "PRODUCE": "38",
        "MIMP": "39",
        "MIDIS": "40",
    }
    for k, cod in alias.items():
        if k in query:
            return cod, SECTORES_GOBIERNO_NACIONAL[cod]

    return "", ministerio_o_codigo


def _limpiar_numero(val: str) -> float | None:
    if not val or val == "&nbsp;":
        return 0.0
    val_clean = val.replace(",", "").replace("&nbsp;", "").strip()
    try:
        return float(val_clean)
    except ValueError:
        return None


def _parsear_tabla_html(html: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Extrae las filas y columnas de la tabla .Data de Consulta Amigable."""
    match = re.search(r'<table[^>]*class=["\']Data["\'][^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
    if not match:
        return [], []

    table_content = match.group(1)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_content, re.DOTALL | re.IGNORECASE)
    if not rows:
        return [], []

    columnas_estandar = [
        "codigo_descripcion", "pia", "pim", "certificacion",
        "compromiso_anual", "compromiso_mensual", "devengado", "girado", "avance_porcentaje"
    ]

    resultado: list[dict[str, Any]] = []
    for row in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL | re.IGNORECASE)
        clean = [re.sub(r'<[^>]+>', '', c).strip().replace('&nbsp;', '') for c in cells]
        if len(clean) < 9:
            continue

        # La celda 0 es la del radio button o vacía, la celda 1 es la descripción
        desc = clean[1]
        pia = _limpiar_numero(clean[2])
        pim = _limpiar_numero(clean[3])
        cert = _limpiar_numero(clean[4])
        comp_anual = _limpiar_numero(clean[5])
        comp_mensual = _limpiar_numero(clean[6])
        devengado = _limpiar_numero(clean[7])
        girado = _limpiar_numero(clean[8])
        avance = _limpiar_numero(clean[9]) if len(clean) > 9 else None

        resultado.append({
            "descripcion": desc,
            "pia": pia,
            "pim": pim,
            "certificacion": cert,
            "compromiso_anual": comp_anual,
            "compromiso_mensual": comp_mensual,
            "devengado": devengado,
            "girado": girado,
            "avance_porcentaje": avance if avance is not None else (round((devengado / pim * 100), 2) if pim else 0.0)
        })

    return columnas_estandar, resultado


def exportar_filas_a_excel(
    datos: list[dict[str, Any]],
    titulo: str,
    nombre_archivo: str = ""
) -> str:
    """Exporta una lista de diccionarios con formato presupuestal a un archivo Excel estilizado."""
    filename = core._output_path(nombre_archivo or titulo, ".xlsx", default="consulta_amigable")
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Consulta Amigable"

    # Encabezado principal
    ws.merge_cells("A1:I1")
    top_cell = ws["A1"]
    top_cell.value = f"MEF - CONSULTA AMIGABLE: {titulo.upper()}"
    top_cell.font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
    top_cell.fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    top_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    # Fila de metadatos
    ws.merge_cells("A2:I2")
    sub_cell = ws["A2"]
    sub_cell.value = f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Fuente: apps5.mineco.gob.pe"
    sub_cell.font = Font(name="Segoe UI", size=9, italic=True, color="555555")
    sub_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 18

    headers = [
        "Descripción / Clasificador", "PIA (S/)", "PIM (S/)", "Certificación (S/)",
        "Compromiso Anual (S/)", "Compromiso Mensual (S/)", "Devengado (S/)", "Girado (S/)", "% Avance"
    ]
    ws.append([])  # fila 3 vacía
    ws.append(headers)  # fila 4 cabeceras
    ws.row_dimensions[4].height = 24

    thin_border = Border(
        left=Side(style='thin', color='DDDDDD'),
        right=Side(style='thin', color='DDDDDD'),
        top=Side(style='thin', color='DDDDDD'),
        bottom=Side(style='thin', color='DDDDDD')
    )

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=4, column=col_idx)
        cell.font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="244061", end_color="244061", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    num_format = "#,##0.00"
    for item in datos:
        row_vals = [
            item.get("descripcion", ""),
            item.get("pia", 0.0),
            item.get("pim", 0.0),
            item.get("certificacion", 0.0),
            item.get("compromiso_anual", 0.0),
            item.get("compromiso_mensual", 0.0),
            item.get("devengado", 0.0),
            item.get("girado", 0.0),
            item.get("avance_porcentaje", 0.0),
        ]
        ws.append(row_vals)
        current_row = ws.max_row
        ws.row_dimensions[current_row].height = 20

        for c_idx in range(1, 10):
            c = ws.cell(row=current_row, column=c_idx)
            c.font = Font(name="Segoe UI", size=10)
            c.border = thin_border
            if c_idx >= 2 and c_idx <= 8:
                c.number_format = num_format
                c.alignment = Alignment(horizontal="right", vertical="center")
            elif c_idx == 9:
                c.number_format = "0.0%"
                if isinstance(c.value, (int, float)):
                    c.value = c.value / 100.0
                c.alignment = Alignment(horizontal="right", vertical="center")
            else:
                c.alignment = Alignment(horizontal="left", vertical="center")

    # Autoajuste de columnas ignorando filas fusionadas
    from openpyxl.utils import get_column_letter

    for col_idx in range(1, 10):
        col_letter = get_column_letter(col_idx)
        max_len = 0
        for row_idx in range(4, ws.max_row + 1):
            val = ws.cell(row=row_idx, column=col_idx).value
            if val is not None:
                max_len = max(max_len, len(str(val)))
        ws.column_dimensions[col_letter].width = max(max_len + 3, 14)
    ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width, 36)

    # Congelar encabezados
    ws.freeze_panes = "A5"

    wb.save(filename)
    return filename


async def consultar_amigable(
    anio: int = 2024,
    ministerio: str = "",
    mes: int | None = None,
    nivel_gobierno: str = "E",
    export_excel: bool = False,
    nombre_excel: str = "",
    tipo: str = "mensual",
) -> dict[str, Any]:
    """Consulta en tiempo real la ejecución presupuestal en el portal Consulta Amigable MEF.

    Parámetros:
    - `anio`: Año fiscal (ej. 2024, 2025, 2026).
    - `ministerio`: Nombre o código del sector (ej. 'SALUD', '11', 'EDUCACION', 'MTC'). Si está vacío, lista todos los sectores.
    - `mes`: Mes específico (1 a 12). Si se define, desglosa o filtra la ejecución por mes.
    - `nivel_gobierno`: 'E' (Gobierno Nacional/Ministerios), 'R' (Gobiernos Regionales), 'M' (Gobiernos Locales).
    - `export_excel`: Si es True, guarda los resultados directamente en un archivo Excel (.xlsx).
    - `tipo`: 'mensual' (corte consolidado mensual en Navegar_6.aspx) o 'diaria' (seguimiento diario actualizado cada noche en Navegar_7.aspx).
    """
    cod_sector, nombre_sector = resolver_sector(ministerio) if ministerio else ("", "")
    endpoint = BASE_URL_DIARIA if tipo.lower() in ("diaria", "diario", "dia") else BASE_URL_MENSUAL

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }

    params = {
        "_tgt": "json",
        "_uhc": "yes",
        "y": str(anio),
        "cpage": "1",
        "psize": "1000",
    }

    # Determinamos la llamada
    if not cod_sector:
        # Consulta de todos los sectores / ministerios en ese nivel de gobierno
        params["1"] = nivel_gobierno
        params["2"] = ""
    else:
        # Consulta de un ministerio específico
        params["1"] = nivel_gobierno
        params["2"] = cod_sector
        params["3"] = ""

    async with httpx.AsyncClient(verify=False, headers=headers, timeout=25.0) as client:
        r = await client.get(endpoint, params=params)
        if r.status_code != 200:
            return {"error": f"Error del portal MEF: código de respuesta HTTP {r.status_code}"}

        # Extraer fecha de actualización del portal si existe
        fecha_corte = ""
        m_lbl = re.search(r'id=["\']ctl00_CPH1_LblLastUpdate["\'][^>]*>([^<]+)<', r.text)
        if m_lbl:
            fecha_corte = m_lbl.group(1).strip()
        else:
            m_txt = re.search(r'(?:[úu]ltima\s+actualizaci[óo]n:?\s*(?:<b>)?\s*)([^<.]+)', r.text, re.IGNORECASE)
            if m_txt:
                fecha_corte = m_txt.group(1).strip()

        # Si se solicitó desglose mensual para un ministerio específico o a nivel general:
        if mes is not None or (cod_sector and "ctl00_CPH1_BtnMes" in r.text):
            # Para desglosar por mes, requerimos el postback con el viewstate
            viewstate_match = re.search(r'name="__VIEWSTATE" id="__VIEWSTATE" value="([^"]*)"', r.text)
            eventval_match = re.search(r'name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="([^"]*)"', r.text)

            if viewstate_match and eventval_match:
                viewstate = viewstate_match.group(1)
                eventval = eventval_match.group(1)

                post_data: dict[str, str] = {
                    "__VIEWSTATE": viewstate,
                    "__EVENTVALIDATION": eventval,
                    "ctl00$CPH1$BtnMes": "Mes"
                }

                # Si estábamos en la lista de sectores y queremos filtrar por uno
                if not cod_sector and ministerio:
                    # buscar radio button del sector
                    for tr in re.finditer(r'<tr[^>]*id=["\']tr\d+["\'][^>]*>(.*?)</tr>', r.text, re.DOTALL):
                        if cod_sector and cod_sector in tr.group(1):
                            val_m = re.search(r'value=["\']([^"\']*)["\']', tr.group(1))
                            if val_m:
                                post_data["grp1"] = val_m.group(1)
                                break

                r_mes = await client.post(str(r.url), data=post_data)
                if r_mes.status_code == 200:
                    _, filas_mes = _parsear_tabla_html(r_mes.text)
                    if filas_mes:
                        # Si se especificó un mes puntual (1 a 12), filtrar solo ese
                        if mes is not None:
                            filas_filtradas = [
                                f for f in filas_mes 
                                if f["descripcion"].startswith(f"{mes}:") or f["descripcion"].lower().startswith(MESES[mes - 1].lower())
                            ]
                            if filas_filtradas:
                                filas_mes = filas_filtradas

                        resp = {
                            "anio": anio,
                            "ministerio": nombre_sector or "TODOS",
                            "nivel_gobierno": nivel_gobierno,
                            "desglose": "mensual",
                            "modulo": tipo,
                            "fecha_actualizacion": fecha_corte,
                            "total_registros": len(filas_mes),
                            "datos": filas_mes
                        }
                        if export_excel:
                            excel_file = exportar_filas_a_excel(
                                filas_mes,
                                f"Gasto {nombre_sector or 'Nacional'} {anio} - Mensual",
                                nombre_archivo=nombre_excel or f"consulta_amigable_{anio}_{cod_sector or 'nacional'}_mensual"
                            )
                            resp["archivo_excel"] = excel_file
                        return resp

        # Parseo regular (sectores o pliegos)
        _, filas = _parsear_tabla_html(r.text)
        
        # Si no devolvió nada en `2=cod_sector&3=""`, intentar listar pliegos directamente
        resp = {
            "anio": anio,
            "ministerio": nombre_sector or "TODOS LOS SECTORES",
            "codigo_sector": cod_sector,
            "nivel_gobierno": nivel_gobierno,
            "modulo": tipo,
            "fecha_actualizacion": fecha_corte,
            "total_registros": len(filas),
            "datos": filas
        }
        if export_excel:
            excel_file = exportar_filas_a_excel(
                filas,
                f"Gasto {nombre_sector or 'Nacional'} {anio}",
                nombre_archivo=nombre_excel or f"consulta_amigable_{anio}_{cod_sector or 'nacional'}"
            )
            resp["archivo_excel"] = excel_file
        return resp


async def consultar_amigable_pliegos(
    anio: int = 2024,
    ministerio: str = "SALUD",
    export_excel: bool = False,
    nombre_excel: str = "",
    tipo: str = "mensual",
) -> dict[str, Any]:
    """Obtiene los pliegos (instituciones) ejecutores dentro de un ministerio específico."""
    cod_sector, nombre_sector = resolver_sector(ministerio)
    if not cod_sector:
        return {"error": f"No se pudo identificar el sector o ministerio '{ministerio}'."}

    endpoint = BASE_URL_DIARIA if tipo.lower() in ("diaria", "diario", "dia") else BASE_URL_MENSUAL
    headers = {"User-Agent": USER_AGENT}
    params = {
        "_tgt": "json",
        "_uhc": "yes",
        "y": str(anio),
        "1": "E",
        "2": cod_sector,
        "3": "",
        "cpage": "1",
        "psize": "1000",
    }

    async with httpx.AsyncClient(verify=False, headers=headers, timeout=25.0) as client:
        r = await client.get(endpoint, params=params)
        if r.status_code != 200:
            return {"error": f"Error del portal MEF: {r.status_code}"}

        fecha_corte = ""
        m_lbl = re.search(r'id=["\']ctl00_CPH1_LblLastUpdate["\'][^>]*>([^<]+)<', r.text)
        if m_lbl:
            fecha_corte = m_lbl.group(1).strip()

        _, filas = _parsear_tabla_html(r.text)
        resp = {
            "anio": anio,
            "sector": nombre_sector,
            "codigo_sector": cod_sector,
            "modulo": tipo,
            "fecha_actualizacion": fecha_corte,
            "total_pliegos": len(filas),
            "pliegos": filas
        }
        if export_excel:
            excel_file = exportar_filas_a_excel(
                filas,
                f"Pliegos {nombre_sector} {anio}",
                nombre_archivo=nombre_excel or f"pliegos_{nombre_sector.lower().replace(' ', '_')}_{anio}"
            )
            resp["archivo_excel"] = excel_file
        return resp
