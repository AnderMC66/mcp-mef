# MCP-MEF (Perú): CLI + Servidor MCP

Herramienta para interactuar con los datos abiertos del **Ministerio de Economía y Finanzas (MEF)** del Perú, disponible de dos formas que comparten la misma base de datos y lógica:

- **CLI nativo (`mef`):** instalable globalmente, se invoca desde cualquier terminal como cualquier otro comando del sistema.
- **Servidor MCP:** para que un LLM (ej. Claude Desktop) descargue datasets, ejecute SQL y genere informes desde el chat.

Ambos permiten descargar dinámicamente conjuntos de datos desde la API oficial de Datos Abiertos del MEF (CKAN) hacia una base de datos local SQLite, ejecutar consultas SQL nativas para análisis económicos, y generar informes en **Markdown, PDF, Excel y HTML**.

Los datos (`mef_data.db`) y los informes generados (`output/`) se guardan en `~/.mcp-mef` (`%USERPROFILE%\.mcp-mef` en Windows), independientemente de si los generaste con el CLI o desde Claude Desktop.

## Características Principales

- **Búsqueda Integrada:** Busca recursos y conjuntos de datos directamente usando palabras clave (ej. "canon").
- **Extracción de Datos con Paginación:** Descarga cualquier dataset oficial usando su `resource_id`, paginando automáticamente hasta reunir el total de registros pedidos, con detección automática de tipos de columna (INTEGER/REAL/TEXT).
- **Motor SQL Integrado:** Los datos se guardan en una base de datos `mef_data.db` (SQLite) para que el LLM pueda hacer joins, agrupaciones y análisis complejos.
- **Trazabilidad:** Cada descarga queda registrada (tabla, `resource_id`, fecha, nº de filas) para que los informes puedan citar su fuente automáticamente.
- **Catálogo de datasets:** Guarda alias memorables hacia `resource_id` ya verificados, para no tener que rebuscar en el portal cada vez.
- **Resumen exploratorio (EDA):** Nº de filas, nulos, valores distintos y estadísticas (min/max/promedio) de cualquier tabla descargada.
- **Informes en Markdown, PDF, HTML y Excel:** Cualquier consulta SQL se puede convertir en un informe (tabla + título + fecha + fuente) sin scripts externos.
- **Gráficos:** vía QuickChart (URL online) o generados localmente con matplotlib (PNG, sin depender de internet, ideal para incrustar en PDFs).
- **Rápido y Ligero:** Construido usando `FastMCP` de Anthropic y `uv` para una gestión rápida del entorno.

## Requisitos Previos

- [uv](https://github.com/astral-sh/uv) instalado.
- Python 3.14 o superior.

## Instalación

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/rodrigocapiz67-tech/mcp-mef.git
   cd mcp-mef
   ```

2. **Instalar el CLI globalmente con `uv tool`:**
   ```bash
   uv tool install --editable .
   ```
   Esto deja disponible el comando `mef` en tu terminal desde cualquier directorio (usa `--editable` para que los cambios que hagas en el repo se reflejen sin reinstalar; usa `uv tool upgrade mcp-mef` o reinstala si actualizas dependencias).

   Verifica que quedó en el PATH con:
   ```bash
   mef --help
   ```
   Si el comando no se encuentra, corre `uv tool update-shell` y abre una terminal nueva.

3. *(Opcional, solo si además quieres usarlo desde Claude Desktop)* **Configurar el servidor MCP:**
   Añade lo siguiente a tu archivo de configuración (ej. `claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "mef-siaf": {
         "command": "uv",
         "args": [
           "run",
           "--directory",
           "Ruta/Absoluta/A/Este/Repositorio",
           "main.py"
         ]
       }
     }
   }
   ```
   *(Asegúrate de cambiar `Ruta/Absoluta/A/Este/Repositorio` por la ruta real donde clonaste este proyecto).* El CLI y el servidor MCP comparten la misma base de datos en `~/.mcp-mef`, así que lo que descargues con uno lo puedes consultar con el otro.

## Uso del CLI

Corre `mef` sin argumentos para ver una portada con el resumen de capacidades y la lista completa
de comandos agrupada por categoría (Búsqueda y Descarga, Consulta y Exploración, Informes y
Gráficos, Catálogo y Exportación). `mef --version` muestra la versión instalada.

```bash
mef search "canon minero"                                  # buscar datasets
mef fetch <resource_id> canon_minero --limit 50000          # descargar (pagina automático)
mef schema                                                   # ver tablas disponibles
mef summary canon_minero                                    # resumen exploratorio (EDA)
mef sql "SELECT * FROM canon_minero LIMIT 5"                 # SQL libre
mef report "SELECT ..." "Mi informe" --formats markdown,pdf  # informe en output/
mef export excel "SELECT ..." --filename mi_reporte          # exportar a Excel
mef export csv "SELECT ..." mi_reporte.csv                   # exportar a CSV
mef chart-local "SELECT ..." bar "Mi gráfico"                # PNG local con matplotlib
mef alias add canon_2025 <resource_id> -d "Canon minero 2025"
mef alias list
```

Cada subcomando tiene su propio `--help` (ej. `mef fetch --help`).

## Herramientas (Tools) Expuestas al LLM vía MCP

El servidor MCP expone las siguientes herramientas (equivalentes 1 a 1 a los subcomandos de `mef`). Todos los archivos que generan (CSV, Excel, PDF, Markdown, HTML, PNG) se guardan en `~/.mcp-mef/output/`.

**Búsqueda y descarga de datos**
* `mef_search_datasets(query)`: Busca datasets relevantes en el portal de datos abiertos del MEF (por ejemplo, al buscar "canon").
* `fetch_mef_dataset(resource_id, table_name, limit, page_size)`: Descarga un recurso del portal `datosabiertos.mef.gob.pe` usando su ID, paginando automáticamente hasta `limit` registros, y lo inserta como tabla en SQLite con tipos de columna detectados automáticamente.
* `mef_register_dataset_alias(alias, resource_id, description)`: Guarda un alias memorable hacia un `resource_id` ya verificado.
* `mef_list_known_datasets()`: Lista los datasets registrados previamente con `mef_register_dataset_alias`.

**Consulta y exploración**
* `sql_mef_db(query)`: Ejecuta comandos SQL sobre la base de datos local y retorna los resultados en JSON estructurado.
* `mef_get_schema()`: Lista las tablas disponibles, sus columnas, nº de filas y metadata de descarga.
* `mef_dataset_summary(table_name)`: Resumen exploratorio (EDA) de una tabla: nulos, valores distintos, min/max/promedio por columna.

**Informes y exportación**
* `mef_generate_report(query, title, formats, filename_base)`: Genera un informe (tabla + título + fecha + fuente) en `markdown`, `pdf` y/o `html` a partir de cualquier consulta SQL.
* `mef_export_csv(query, filename)`: Exporta resultados de una consulta a CSV.
* `mef_export_excel(query, filename)`: Exporta resultados de una consulta a un archivo `.xlsx` con encabezados en negrita y columnas autoajustadas.

**Gráficos**
* `mef_generate_chart(query, chart_type, title)`: Genera un gráfico vía QuickChart y retorna una URL (requiere internet para visualizarlo).
* `mef_generate_chart_local(query, chart_type, title, filename)`: Genera un gráfico PNG local con matplotlib, sin depender de servicios externos — ideal para incrustar en informes.

## Generación de Dashboards (legacy)

El repositorio conserva dos scripts standalone, específicos para la tabla `canon_minero`, útiles como referencia de estilo (deben correrse con `uv run python <script>.py` desde el repo, ya que importan `mcp_mef.core` para ubicar la base de datos):

* `uv run python generate_report.py`: Genera un reporte HTML sencillo con los Tops de recaudación/ingresos (`informe_canon_minero.html`).
* `uv run python generate_report_advanced.py`: Genera un dashboard interactivo avanzado (usando Chart.js) con gráficos de evolución por mes, barras y gráficos de dona mostrando la distribución del canon (`informe_canon_minero_avanzado.html`).

Para cualquier otra tabla o consulta, usa `mef report` (CLI) o la tool `mef_generate_report` (MCP) en vez de estos scripts.

## Advertencia

Los datos obtenidos a través de la API provienen directamente del portal oficial de Datos Abiertos del Gobierno Peruano, pero este proyecto no está afiliado oficialmente al Ministerio de Economía y Finanzas (MEF).
