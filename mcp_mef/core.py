"""Lógica de negocio del MCP-MEF, compartida entre el servidor MCP (server.py) y el CLI (cli.py).

Estas funciones no son tools de MCP -- son las implementaciones puras. server.py las expone
como @mcp.tool() y cli.py las expone como subcomandos de terminal.
"""
import httpx
import sqlite3
import json
import re
import os
import csv
import urllib.parse
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from jinja2 import Template
from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Font

# Directorio de datos del usuario: fijo, independiente de dónde viva el código instalado.
# Así el CLI global ("mef ...") y el servidor MCP para Claude Desktop comparten la misma base
# de datos y los mismos informes, sin importar cómo se invoque cada uno.
APP_DIR = Path(os.environ.get("MCP_MEF_HOME", str(Path.home() / ".mcp-mef")))
APP_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = str(APP_DIR / "mef_data.db")
OUTPUT_DIR = str(APP_DIR / "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TABLE_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _validate_table_name(name: str) -> None:
    if not TABLE_NAME_RE.match(name):
        raise ValueError(
            f"Nombre de tabla inválido: '{name}'. Usa solo letras, números y guion bajo, sin empezar con número."
        )
    if name.startswith("_meta"):
        raise ValueError("Los nombres de tabla que empiezan con '_meta' están reservados para uso interno.")


def _slugify(text: str) -> str:
    text = re.sub(r'[^\w\s-]', '', text, flags=re.UNICODE).strip().lower()
    text = re.sub(r'[-\s]+', '_', text)
    return text or "reporte"


def _infer_sql_type(values: list[str]) -> str:
    non_empty = [v for v in values if v not in (None, "")]
    if not non_empty:
        return "TEXT"

    # Los códigos con ceros a la izquierda (ubigeo, códigos de entidad, etc.) deben
    # conservarse como TEXT o se pierde información al convertir a número.
    if any(len(v) > 1 and v[0] == '0' and v.lstrip('-').isdigit() for v in non_empty):
        return "TEXT"

    def _is_int(v: str) -> bool:
        try:
            int(v)
            return True
        except ValueError:
            return False

    def _is_float(v: str) -> bool:
        try:
            float(v)
            return True
        except ValueError:
            return False

    if all(_is_int(v) for v in non_empty):
        return "INTEGER"
    if all(_is_float(v) for v in non_empty):
        return "REAL"
    return "TEXT"


def _convert_value(v, sql_type: str):
    if v is None or v == "":
        return None
    try:
        if sql_type == "INTEGER":
            return int(v)
        if sql_type == "REAL":
            return float(v)
    except (ValueError, TypeError):
        return str(v)
    return str(v)


def _register_download(cursor: sqlite3.Cursor, table_name: str, resource_id: str, row_count: int) -> None:
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS _meta_downloads (
            table_name TEXT PRIMARY KEY,
            resource_id TEXT,
            source_url TEXT,
            fetched_at TEXT,
            row_count INTEGER
        )
    ''')
    source_url = f"https://api.datosabiertos.mef.gob.pe/DatosAbiertos/v1/datastore_search?resource_id={resource_id}"
    cursor.execute('''
        INSERT INTO _meta_downloads (table_name, resource_id, source_url, fetched_at, row_count)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(table_name) DO UPDATE SET
            resource_id=excluded.resource_id,
            source_url=excluded.source_url,
            fetched_at=excluded.fetched_at,
            row_count=excluded.row_count
    ''', (table_name, resource_id, source_url, datetime.now().isoformat(timespec="seconds"), row_count))


def _lookup_source_info(cursor: sqlite3.Cursor, query: str) -> dict | None:
    match = re.search(r'FROM\s+"?([A-Za-z_][A-Za-z0-9_]*)"?', query, re.IGNORECASE)
    if not match:
        return None
    table = match.group(1)
    try:
        cursor.execute(
            "SELECT resource_id, source_url, fetched_at FROM _meta_downloads WHERE table_name = ?", (table,)
        )
        row = cursor.fetchone()
        if row:
            return {"tabla": table, "resource_id": row[0], "source_url": row[1], "fetched_at": row[2]}
    except sqlite3.OperationalError:
        pass
    return None


def _safe_pdf_text(s: str) -> str:
    # Las fuentes core de fpdf2 (Helvetica) sólo soportan latin-1.
    return str(s).encode('latin-1', 'replace').decode('latin-1')


def _build_markdown_report(title, columns, rows, generated_at, source_info) -> str:
    lines = [f"# {title}", "", f"*Generado: {generated_at}*"]
    if source_info:
        lines.append(
            f"*Fuente: resource_id `{source_info['resource_id']}` (tabla `{source_info['tabla']}`, descargada {source_info['fetched_at']})*"
        )
    lines.append("")
    lines.append("| " + " | ".join(str(c) for c in columns) + " |")
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")
    for r in rows:
        lines.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    lines.append("")
    lines.append(f"_Total de filas: {len(rows)}_")
    return "\n".join(lines)


_HTML_REPORT_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>{{ title }}</title>
<style>
  body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 40px; background:#f4f7f6; color:#333; }
  .container { max-width: 1100px; margin:0 auto; background:#fff; padding:30px; border-radius:8px; box-shadow:0 4px 6px rgba(0,0,0,.1); }
  h1 { color:#2c3e50; border-bottom:2px solid #3498db; padding-bottom:10px; }
  table { width:100%; border-collapse:collapse; margin-top:15px; }
  th, td { padding:10px; text-align:left; border-bottom:1px solid #ddd; font-size:14px; }
  th { background:#3498db; color:#fff; }
  tr:hover { background:#f1f1f1; }
  .meta { color:#7f8c8d; font-size:12px; margin-top:6px; }
  .footer { text-align:center; margin-top:30px; font-size:12px; color:#7f8c8d; }
</style>
</head>
<body>
<div class="container">
  <h1>{{ title }}</h1>
  <div class="meta">
    Generado: {{ generated_at }}
    {% if source_info %} &middot; Fuente: resource_id {{ source_info.resource_id }} (descargado {{ source_info.fetched_at }}){% endif %}
  </div>
  <table>
    <thead><tr>{% for c in columns %}<th>{{ c }}</th>{% endfor %}</tr></thead>
    <tbody>
    {% for row in rows %}
      <tr>{% for v in row %}<td>{{ v if v is not none else "" }}</td>{% endfor %}</tr>
    {% endfor %}
    </tbody>
  </table>
  <div class="footer">Total de filas: {{ rows|length }} &middot; Generado automáticamente por MCP-MEF</div>
</div>
</body>
</html>
""")


def _build_html_report(title, columns, rows, generated_at, source_info) -> str:
    return _HTML_REPORT_TEMPLATE.render(
        title=title, columns=columns, rows=rows, generated_at=generated_at, source_info=source_info
    )


def _build_pdf_report(title, columns, rows, generated_at, source_info, path) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, _safe_pdf_text(title), new_x="LMARGIN", new_y="NEXT")

    meta = f"Generado: {generated_at}"
    if source_info:
        meta += f" | Fuente: resource_id {source_info['resource_id']} (descargado {source_info['fetched_at']})"
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 6, _safe_pdf_text(meta), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 8)
    with pdf.table() as table:
        header = table.row()
        for c in columns:
            header.cell(_safe_pdf_text(c))
        for r in rows:
            trow = table.row()
            for v in r:
                trow.cell(_safe_pdf_text("" if v is None else v))

    pdf.set_font("Helvetica", "I", 8)
    pdf.ln(4)
    pdf.cell(0, 6, f"Total de filas: {len(rows)}", ln=True)
    pdf.output(path)


# ---------------------------------------------------------------------------
# Operaciones (usadas por server.py como tools MCP y por cli.py como comandos)
# ---------------------------------------------------------------------------

async def fetch_mef_dataset(resource_id: str, table_name: str, limit: int = 1000, page_size: int = 1000) -> str:
    try:
        _validate_table_name(table_name)
    except ValueError as e:
        return f"Error: {e}"

    all_records: list[dict] = []
    offset = 0
    warning = ""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(all_records) < limit:
                batch_limit = min(page_size, limit - len(all_records))
                url = (
                    "https://api.datosabiertos.mef.gob.pe/DatosAbiertos/v1/datastore_search"
                    f"?resource_id={resource_id}&limit={batch_limit}&offset={offset}"
                )
                response = await client.get(url)
                if response.status_code != 200:
                    if all_records:
                        warning = f" (advertencia: se detuvo la paginación por error HTTP {response.status_code})"
                        break
                    return f"Error HTTP {response.status_code}: {response.text}"

                data = response.json()
                records = data.get("records", [])
                if not records and "result" in data and "records" in data["result"]:
                    records = data["result"]["records"]

                if not records:
                    break

                all_records.extend(records)
                offset += len(records)
                if len(records) < batch_limit:
                    break  # última página
    except Exception as e:
        if all_records:
            warning = f" (advertencia: se detuvo la descarga por una excepción: {e})"
        else:
            return f"Excepción al descargar dataset: {str(e)}"

    if not all_records:
        return "No se encontraron registros o la API del MEF indicó error."

    columns = list(all_records[0].keys())
    col_types = {
        col: _infer_sql_type([str(r.get(col)) if r.get(col) is not None else "" for r in all_records])
        for col in columns
    }

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cols_def = ", ".join(f'"{col}" {col_types[col]}' for col in columns)
    cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    cursor.execute(f'CREATE TABLE "{table_name}" ({cols_def})')

    placeholders = ", ".join(["?" for _ in columns])
    insert_query = f'INSERT INTO "{table_name}" VALUES ({placeholders})'
    for row in all_records:
        values = [_convert_value(row.get(col), col_types[col]) for col in columns]
        cursor.execute(insert_query, values)

    _register_download(cursor, table_name, resource_id, len(all_records))

    conn.commit()
    conn.close()

    tipos = ", ".join(f"{c}:{t}" for c, t in col_types.items())
    return (
        f"Éxito: se guardaron {len(all_records)} registros reales en la tabla '{table_name}'{warning}.\n"
        f"Tipos detectados -> {tipos}"
    )


async def mef_search_datasets(query: str) -> str:
    url = f"https://www.datosabiertos.gob.pe/api/3/action/package_search?q={urllib.parse.quote(query)}"

    try:
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            response = await client.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30.0)
            if response.status_code != 200:
                return f"Error HTTP {response.status_code}: {response.text}"

            data = response.json()
            if data.get("success"):
                results = data.get("result", {}).get("results", [])
                out = []
                for pkg in results[:10]:
                    resources = pkg.get("resources", [])
                    for res in resources:
                        if res.get("format", "").upper() in ["CSV", "JSON", "XLS", "XLSX"]:
                            out.append({
                                "titulo_dataset": pkg.get("title"),
                                "recurso": res.get("name") or res.get("description"),
                                "formato": res.get("format"),
                                "resource_id": res.get("id")
                            })
                if not out:
                    return "No se encontraron recursos en formato tabular (CSV, JSON, XLS) para tu búsqueda."
                return json.dumps(out[:20], indent=2, ensure_ascii=False)
            else:
                return "La API de datos abiertos devolvió un error en la búsqueda."
    except Exception as e:
        return f"Excepción al buscar dataset: {str(e)}"


def mef_register_dataset_alias(alias: str, resource_id: str, description: str = "") -> str:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS _meta_catalog (
            alias TEXT PRIMARY KEY,
            resource_id TEXT,
            description TEXT,
            registered_at TEXT
        )
    ''')
    cursor.execute('''
        INSERT INTO _meta_catalog (alias, resource_id, description, registered_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(alias) DO UPDATE SET
            resource_id=excluded.resource_id,
            description=excluded.description,
            registered_at=excluded.registered_at
    ''', (alias, resource_id, description, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()
    return f"Alias '{alias}' registrado -> resource_id '{resource_id}'."


def mef_list_known_datasets() -> str:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_meta_catalog'")
    if not cursor.fetchone():
        conn.close()
        return "Aún no hay datasets registrados. Usa mef_register_dataset_alias tras encontrar uno con mef_search_datasets."

    cursor.execute("SELECT alias, resource_id, description, registered_at FROM _meta_catalog ORDER BY registered_at DESC")
    rows = cursor.fetchall()
    conn.close()
    catalog = [
        {"alias": a, "resource_id": r, "descripcion": d, "registrado": t}
        for a, r, d, t in rows
    ]
    return json.dumps(catalog, indent=2, ensure_ascii=False)


def sql_mef_db(query: str) -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)

        if query.strip().upper().startswith("SELECT"):
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            conn.close()
            return json.dumps({"columnas": columns, "filas": results}, indent=2, ensure_ascii=False, default=str)
        else:
            conn.commit()
            conn.close()
            return json.dumps({"status": "success", "message": "Consulta ejecutada correctamente."})

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def mef_get_schema() -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '\\_meta%' ESCAPE '\\'")
        tables = [row[0] for row in cursor.fetchall()]

        schema = {}
        for table in tables:
            cursor.execute(f'PRAGMA table_info("{table}")')
            columns = [row[1] for row in cursor.fetchall()]
            cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
            row_count = cursor.fetchone()[0]
            entry = {"columnas": columns, "filas": row_count}
            try:
                cursor.execute(
                    "SELECT resource_id, fetched_at FROM _meta_downloads WHERE table_name = ?", (table,)
                )
                meta = cursor.fetchone()
                if meta:
                    entry["resource_id"] = meta[0]
                    entry["descargado"] = meta[1]
            except sqlite3.OperationalError:
                pass
            schema[table] = entry

        conn.close()
        return json.dumps(schema, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error al obtener el esquema: {str(e)}"


def mef_dataset_summary(table_name: str) -> str:
    try:
        _validate_table_name(table_name)
    except ValueError as e:
        return f"Error: {e}"

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        cols = cursor.fetchall()
        if not cols:
            conn.close()
            return f"La tabla '{table_name}' no existe."

        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        total = cursor.fetchone()[0]

        summary = {"tabla": table_name, "total_filas": total, "columnas": {}}
        for _, name, ctype, _, _, _ in cols:
            col_info = {"tipo": ctype}
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}" WHERE "{name}" IS NULL')
            col_info["nulos"] = cursor.fetchone()[0]
            cursor.execute(f'SELECT COUNT(DISTINCT "{name}") FROM "{table_name}"')
            col_info["valores_distintos"] = cursor.fetchone()[0]
            if ctype in ("INTEGER", "REAL"):
                cursor.execute(f'SELECT MIN("{name}"), MAX("{name}"), AVG("{name}") FROM "{table_name}"')
                mn, mx, avg = cursor.fetchone()
                col_info["min"] = mn
                col_info["max"] = mx
                col_info["promedio"] = round(avg, 2) if avg is not None else None
            summary["columnas"][name] = col_info

        conn.close()
        return json.dumps(summary, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error al generar el resumen: {str(e)}"


def mef_generate_chart(query: str, chart_type: str, title: str) -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()

        if not results:
            return "La consulta no retornó datos."

        labels = [str(r[0]) for r in results]
        try:
            values = [float(r[1]) for r in results]
        except (ValueError, TypeError):
            return "La segunda columna de la consulta SQL debe ser numérica para poder graficar."

        chart_config = {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": title,
                    "data": values
                }]
            },
            "options": {
                "title": {
                    "display": True,
                    "text": title
                }
            }
        }

        config_json = json.dumps(chart_config)
        encoded_config = urllib.parse.quote(config_json)
        url = f"https://quickchart.io/chart?c={encoded_config}"

        return f"Gráfico generado con éxito. URL: {url}"
    except Exception as e:
        return f"Error al generar gráfico: {str(e)}"


def mef_generate_chart_local(query: str, chart_type: str, title: str, filename: str = "") -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
    except Exception as e:
        return f"Error al ejecutar la consulta: {e}"

    if not results:
        return "La consulta no retornó datos."

    labels = [str(r[0]) for r in results]
    try:
        values = [float(r[1]) for r in results]
    except (ValueError, TypeError):
        return "La segunda columna de la consulta SQL debe ser numérica para poder graficar."

    fig, ax = plt.subplots(figsize=(8, 5))
    if chart_type == "bar":
        ax.bar(labels, values, color="#3b82f6")
        plt.xticks(rotation=45, ha="right")
    elif chart_type == "pie":
        ax.pie(values, labels=labels, autopct="%1.1f%%")
    elif chart_type == "line":
        ax.plot(labels, values, marker="o", color="#3b82f6")
        plt.xticks(rotation=45, ha="right")
    else:
        plt.close(fig)
        return "chart_type debe ser 'bar', 'pie' o 'line'."

    ax.set_title(title)
    fig.tight_layout()

    name = _slugify(filename or title)
    path = os.path.join(OUTPUT_DIR, f"{name}.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)

    return f"Gráfico generado: {path}"


def mef_generate_report(query: str, title: str, formats: list[str] | None = None, filename_base: str = "") -> str:
    if formats is None:
        formats = ["markdown"]

    if not query.strip().upper().startswith("SELECT"):
        return "Error: mef_generate_report solo acepta consultas SELECT."

    valid_formats = {"markdown", "pdf", "html"}
    formats = [f for f in formats if f in valid_formats]
    if not formats:
        return "Error: 'formats' debe incluir al menos uno de: 'markdown', 'pdf', 'html'."

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        source_info = _lookup_source_info(cursor, query)
        conn.close()
    except Exception as e:
        return f"Error al ejecutar la consulta: {e}"

    if not rows:
        return "La consulta no retornó filas; no se generó ningún informe."

    base = _slugify(filename_base or title)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    outputs = []

    if "markdown" in formats:
        md = _build_markdown_report(title, columns, rows, generated_at, source_info)
        path = os.path.join(OUTPUT_DIR, f"{base}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        outputs.append(path)

    if "html" in formats:
        html = _build_html_report(title, columns, rows, generated_at, source_info)
        path = os.path.join(OUTPUT_DIR, f"{base}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        outputs.append(path)

    if "pdf" in formats:
        path = os.path.join(OUTPUT_DIR, f"{base}.pdf")
        _build_pdf_report(title, columns, rows, generated_at, source_info, path)
        outputs.append(path)

    return "Informe generado:\n" + "\n".join(outputs)


def mef_export_csv(query: str, filename: str) -> str:
    try:
        if not filename.endswith('.csv'):
            filename += '.csv'

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)

        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()

        filepath = os.path.join(OUTPUT_DIR, filename)

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(results)

        return f"Éxito. Datos exportados correctamente a {filepath} ({len(results)} filas)."
    except Exception as e:
        return f"Error al exportar CSV: {str(e)}"


def mef_export_excel(query: str, filename: str = "") -> str:
    if not query.strip().upper().startswith("SELECT"):
        return "Error: mef_export_excel solo acepta consultas SELECT."

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        conn.close()
    except Exception as e:
        return f"Error al ejecutar la consulta: {e}"

    if not rows:
        return "La consulta no retornó filas."

    wb = Workbook()
    ws = wb.active
    ws.title = "Datos"
    ws.append(columns)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(list(row))

    for i, col in enumerate(columns, start=1):
        max_len = max([len(str(col))] + [len(str(r[i - 1])) for r in rows if r[i - 1] is not None] or [0])
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(max_len + 2, 50)

    name = filename.strip() if filename else "reporte"
    if name.lower().endswith(".xlsx"):
        name = name[:-5]
    name = _slugify(name)

    path = os.path.join(OUTPUT_DIR, f"{name}.xlsx")
    wb.save(path)

    return f"Éxito. Datos exportados a {path} ({len(rows)} filas)."
