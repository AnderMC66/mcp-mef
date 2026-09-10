"""Servidor MCP (FastMCP) para Claude Desktop y otros clientes MCP.

Cada tool es un wrapper delgado sobre mcp_mef.core -- la misma lógica que usa el CLI (cli.py),
para que ambos compartan comportamiento y datos.
"""
from mcp.server.fastmcp import FastMCP

from . import core

mcp = FastMCP("MEF_SIAF")


@mcp.tool()
async def fetch_mef_dataset(
    resource_id: str,
    table_name: str,
    limit: int = 1000,
    page_size: int = 1000,
    offset: int = 0,
) -> str:
    """
    Descarga un dataset del MEF usando su `resource_id` (obtenido con mef_search_datasets /
    mef_list_resources) y lo guarda en la base de datos local (SQLite) bajo `table_name`.
    Si la tabla ya existe, se reemplaza sólo cuando la descarga termina bien.

    Pagina automáticamente hasta reunir `limit` registros (o agotar el dataset) en bloques de
    `page_size` (máximo 20000, que es lo más eficiente), insertando cada página según llega.
    `offset` permite empezar más adelante para traer un dataset grande por tramos.

    IMPORTANTE: llama antes a mef_dataset_info(resource_id). Los datasets de Transparencia
    Económica (Presupuesto y Ejecución de Gasto) tienen millones de filas y traerlos enteros
    puede tardar horas; conviene acordar con el usuario un `limit` razonable.

    Detecta el tipo de cada columna (INTEGER/REAL/TEXT) a partir de la primera página y
    registra la descarga en la tabla interna `_meta_downloads` para trazabilidad.
    """
    return await core.fetch_mef_dataset(resource_id, table_name, limit, page_size, offset)


@mcp.tool()
async def mef_dataset_info(resource_id: str) -> str:
    """
    Consulta cuántas filas y qué columnas tiene un recurso del MEF SIN descargarlo, con una
    fila de muestra. Úsalo siempre antes de fetch_mef_dataset para dimensionar la descarga
    (los datasets de gasto anual superan los 7 millones de filas y 60 columnas).
    """
    return await core.mef_dataset_info(resource_id)


@mcp.tool()
async def mef_list_resources(dataset_slug: str) -> str:
    """
    Lista todos los recursos descargables de un dataset del portal, con su `resource_id`.
    El `dataset_slug` es el campo 'slug' que devuelve mef_search_datasets
    (ej. 'presupuesto-y-ejecucion-de-gasto').

    Es el paso obligado para los datos de Transparencia Económica: esos datasets publican un
    recurso por año (2009-Gasto.csv ... 2026-Gasto-Mensual.csv) más un diccionario de
    variables, cada uno con su propio resource_id.
    """
    return await core.mef_list_resources(dataset_slug)


@mcp.tool()
async def mef_search_datasets(query: str, page: int = 1) -> str:
    """
    Busca datasets dinámicamente en el portal de Datos Abiertos del MEF por palabra clave
    (ej. 'canon minero') y retorna, en JSON, los títulos de los recursos tabulares encontrados
    junto a su 'resource_id', listo para pasar a fetch_mef_dataset.
    """
    return await core.mef_search_datasets(query)


@mcp.tool()
def mef_register_dataset_alias(alias: str, resource_id: str, description: str = "") -> str:
    """
    Registra un alias memorable (ej. 'canon_minero_2025') que apunta a un `resource_id` ya
    verificado (obtenido previamente con mef_search_datasets), para no tener que volver a
    buscarlo cada vez. Se guarda localmente en mef_data.db, y a partir de entonces
    fetch_mef_dataset y mef_dataset_info aceptan ese alias donde esperan un resource_id.
    """
    return core.mef_register_dataset_alias(alias, resource_id, description)


@mcp.tool()
def mef_remove_dataset_alias(alias: str) -> str:
    """
    Borra un alias del catálogo local. No afecta a las tablas ya descargadas.
    """
    return core.mef_remove_dataset_alias(alias)


@mcp.tool()
def mef_list_known_datasets() -> str:
    """
    Lista los datasets registrados previamente con mef_register_dataset_alias, para
    reutilizar su resource_id sin tener que volver a buscarlo con mef_search_datasets.
    """
    return core.mef_list_known_datasets()


@mcp.tool()
def sql_mef_db(query: str, max_rows: int = core.MAX_SQL_ROWS) -> str:
    """
    Ejecuta una consulta SQL nativa en la base de datos local del MEF (mef_data.db).
    Puedes hacer JOINs entre tablas que hayas descargado previamente, y también CTEs
    (`WITH ... SELECT`). Es la única tool que admite sentencias de escritura (CREATE/UPDATE/
    DELETE sobre tablas derivadas); las de informe y exportación solo aceptan lectura.
    Retorna los resultados en formato JSON: {"columnas": [...], "filas": [[...]]}.

    Devuelve como mucho `max_rows` filas (1000 por defecto) y avisa con "truncado": true
    cuando había más. Las tablas descargadas pueden tener millones de filas, así que agrega
    siempre GROUP BY / LIMIT en vez de subir `max_rows`: para volcados completos existen
    mef_export_csv y mef_export_excel.
    """
    return core.sql_mef_db(query, max_rows)


@mcp.tool()
def mef_get_schema() -> str:
    """
    Retorna la estructura de la base de datos local: tablas de datos disponibles, sus columnas,
    número de filas y, cuando existe, la metadata de descarga (resource_id, fecha de descarga).
    Útil para saber qué consultar con sql_mef_db o mef_generate_report.
    """
    return core.mef_get_schema()


@mcp.tool()
def mef_db_stats() -> str:
    """
    Cuánto ocupa en disco la base local, qué tablas contiene y cuántas filas tiene cada una.
    Útil para decidir qué borrar cuando se han descargado varios años de datos de gasto.
    """
    return core.mef_db_stats()


@mcp.tool()
def mef_drop_table(table_name: str, vacuum: bool = False) -> str:
    """
    BORRA una tabla descargada y su registro de trazabilidad. Es destructivo e irreversible:
    confirma con la persona usuaria antes de llamarlo, y recuérdale que volver a descargar el
    dataset puede tardar mucho.

    Con vacuum=True compacta además el archivo para devolver el espacio al sistema (puede
    tardar en bases de varios GB).
    """
    return core.mef_drop_table(table_name, vacuum)


@mcp.tool()
def mef_dataset_summary(table_name: str) -> str:
    """
    Genera un resumen exploratorio (EDA) de una tabla ya descargada: número total de filas,
    y por cada columna su tipo, cantidad de nulos, valores distintos y (si es numérica)
    mínimo, máximo y promedio. Útil antes de decidir qué consultar o graficar.
    """
    return core.mef_dataset_summary(table_name)


@mcp.tool()
def mef_generate_chart(query: str, chart_type: str, title: str) -> str:
    """
    Ejecuta una consulta SQL y genera un gráfico a través de QuickChart (servicio externo).
    La consulta no debe devolver más de 2000 puntos: agrupa con GROUP BY antes de graficar.
    chart_type puede ser 'bar', 'pie', o 'line'.
    La consulta DEBE retornar 2 columnas: la primera para las etiquetas (labels) y la segunda para los valores numéricos.
    Retorna una URL directa a la imagen del gráfico. Requiere conexión a internet para visualizarla.
    Para un gráfico embebible en PDF/HTML sin depender de internet, usa mef_generate_chart_local.
    """
    return core.mef_generate_chart(query, chart_type, title)


@mcp.tool()
def mef_generate_chart_local(query: str, chart_type: str, title: str, filename: str = "") -> str:
    """
    Ejecuta una consulta SQL (debe retornar 2 columnas: etiqueta y valor numérico) y genera un
    gráfico con matplotlib guardado como imagen PNG en ~/.mcp-mef/output, sin depender de
    ningún servicio externo. Ideal para incrustar en informes PDF/HTML offline.
    chart_type: 'bar', 'pie' o 'line'.
    """
    return core.mef_generate_chart_local(query, chart_type, title, filename)


@mcp.tool()
def mef_generate_report(
    query: str,
    title: str,
    formats: list[str] | None = None,
    filename_base: str = "",
    max_rows: int = core.MAX_REPORT_ROWS,
) -> str:
    """
    Ejecuta una consulta de lectura (SELECT o WITH) sobre mef_data.db y genera un informe con
    los resultados en uno o más formatos: 'markdown', 'pdf', 'html' (por defecto, markdown).
    Guarda los archivos en ~/.mcp-mef/output. Cada informe incluye la fecha de generación y, si
    puede detectarse a partir de la tabla usada en el FROM, la fuente/fecha de descarga
    registrada en `_meta_downloads`.
    Como un informe con decenas de miles de filas es inmanejable (sobre todo en PDF), la tabla
    se trunca a `max_rows` filas y el pie del informe indica el total real.
    Retorna las rutas de los archivos generados.
    """
    return core.mef_generate_report(query, title, formats, filename_base, max_rows)


@mcp.tool()
def mef_export_csv(query: str, filename: str) -> str:
    """
    Ejecuta una consulta de lectura (SELECT o WITH) y exporta TODOS los resultados a un CSV
    en ~/.mcp-mef/output, escribiéndolos por lotes (sin tope de filas ni de memoria). `filename` es solo un nombre de archivo (sin rutas); la extensión .csv
    se añade si falta. El archivo se escribe con BOM UTF-8 para que Excel muestre bien las tildes.
    """
    return core.mef_export_csv(query, filename)


@mcp.tool()
def mef_export_excel(query: str, filename: str = "") -> str:
    """
    Ejecuta una consulta de lectura (SELECT o WITH) y exporta el resultado a un archivo Excel
    (.xlsx) en ~/.mcp-mef/output, con encabezados en negrita, fila de títulos congelada y
    columnas autoajustadas. El formato .xlsx no admite más de 1 048 575 filas de datos; si la
    consulta devuelve más, se avisa y conviene usar mef_export_csv.
    """
    return core.mef_export_excel(query, filename)


def run():
    mcp.run(transport='stdio')


if __name__ == "__main__":
    run()
