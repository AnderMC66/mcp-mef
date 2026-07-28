"""Servidor MCP (FastMCP) para Claude Desktop y otros clientes MCP.

Cada tool es un wrapper delgado sobre mcp_mef.core -- la misma lógica que usa el CLI (cli.py),
para que ambos compartan comportamiento y datos.
"""
from mcp.server.fastmcp import FastMCP

from . import core

mcp = FastMCP("MEF_SIAF")


@mcp.tool()
async def fetch_mef_dataset(resource_id: str, table_name: str, limit: int = 1000, page_size: int = 1000) -> str:
    """
    Descarga un dataset del MEF usando su `resource_id` (obtenido desde datosabiertos.mef.gob.pe
    o con mef_search_datasets) y lo guarda en la base de datos local (SQLite) bajo `table_name`.
    Si la tabla ya existe, la sobrescribe.

    Pagina automáticamente la API hasta reunir `limit` registros (o hasta agotar el dataset),
    en bloques de `page_size`. Para descargar un dataset completo, sube `limit` (ej. 50000).
    Detecta automáticamente el tipo de cada columna (INTEGER/REAL/TEXT) y registra la
    descarga en la tabla interna `_meta_downloads` para trazabilidad.
    """
    return await core.fetch_mef_dataset(resource_id, table_name, limit, page_size)


@mcp.tool()
async def mef_search_datasets(query: str) -> str:
    """
    Busca datasets dinámicamente en el portal de datos abiertos.
    Retorna los títulos y los 'resource_id' listos para descargar.
    """
    return await core.mef_search_datasets(query)


@mcp.tool()
def mef_register_dataset_alias(alias: str, resource_id: str, description: str = "") -> str:
    """
    Registra un alias memorable (ej. 'canon_minero_2025') que apunta a un `resource_id` ya
    verificado (obtenido previamente con mef_search_datasets), para no tener que volver a
    buscarlo cada vez. Se guarda localmente en mef_data.db.
    """
    return core.mef_register_dataset_alias(alias, resource_id, description)


@mcp.tool()
def mef_list_known_datasets() -> str:
    """
    Lista los datasets registrados previamente con mef_register_dataset_alias, para
    reutilizar su resource_id sin tener que volver a buscarlo con mef_search_datasets.
    """
    return core.mef_list_known_datasets()


@mcp.tool()
def sql_mef_db(query: str) -> str:
    """
    Ejecuta una consulta SQL nativa en la base de datos local del MEF (mef_data.db).
    Puedes hacer JOINs entre tablas que hayas descargado previamente.
    Retorna los resultados en formato JSON.
    """
    return core.sql_mef_db(query)


@mcp.tool()
def mef_get_schema() -> str:
    """
    Retorna la estructura de la base de datos local: tablas de datos disponibles, sus columnas,
    número de filas y, cuando existe, la metadata de descarga (resource_id, fecha de descarga).
    Útil para saber qué consultar con sql_mef_db o mef_generate_report.
    """
    return core.mef_get_schema()


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
    gráfico con matplotlib guardado como imagen PNG en la carpeta 'output/' del proyecto, sin
    depender de ningún servicio externo. Ideal para incrustar en informes PDF/HTML offline.
    chart_type: 'bar', 'pie' o 'line'.
    """
    return core.mef_generate_chart_local(query, chart_type, title, filename)


@mcp.tool()
def mef_generate_report(query: str, title: str, formats: list[str] = ["markdown"], filename_base: str = "") -> str:
    """
    Ejecuta una consulta SQL SELECT sobre mef_data.db y genera un informe con los resultados
    en uno o más formatos: 'markdown', 'pdf', 'html'. Guarda los archivos en la carpeta 'output/'
    del proyecto. Cada informe incluye la fecha de generación y, si puede detectarse a partir de
    la tabla usada en el FROM, la fuente/fecha de descarga registrada en `_meta_downloads`.
    Retorna las rutas de los archivos generados.
    """
    return core.mef_generate_report(query, title, formats, filename_base)


@mcp.tool()
def mef_export_csv(query: str, filename: str) -> str:
    """
    Ejecuta una consulta SQL en la base de datos local y exporta los resultados a un archivo CSV
    en la carpeta 'output/' del proyecto. filename debe terminar en .csv, por ejemplo 'reporte.csv'.
    """
    return core.mef_export_csv(query, filename)


@mcp.tool()
def mef_export_excel(query: str, filename: str = "") -> str:
    """
    Ejecuta una consulta SQL SELECT y exporta el resultado a un archivo Excel (.xlsx) en la
    carpeta 'output/' del proyecto, con encabezados en negrita y columnas autoajustadas.
    """
    return core.mef_export_excel(query, filename)


def run():
    mcp.run(transport='stdio')


if __name__ == "__main__":
    run()
