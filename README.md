# MCP Server - MEF SIAF (Perú)

Este es un servidor **Model Context Protocol (MCP)** diseñado para interactuar con los datos abiertos del **Ministerio de Economía y Finanzas (MEF)** del Perú. 

Permite a los Modelos de Lenguaje (LLMs) descargar dinámicamente conjuntos de datos desde la API oficial de Datos Abiertos del MEF (CKAN) hacia una base de datos local SQLite, y luego ejecutar consultas SQL nativas para realizar análisis económicos. Además, cuenta con scripts integrados para generar reportes HTML y dashboards interactivos basados en los datos recopilados.

## Características Principales

- **Búsqueda Integrada:** Busca recursos y conjuntos de datos directamente usando palabras clave (ej. "canon").
- **Extracción de Datos Dinámica:** Descarga cualquier dataset oficial usando su `resource_id` y lo convierte automáticamente en tablas SQL.
- **Motor SQL Integrado:** Los datos se guardan en una base de datos `mef_data.db` (SQLite) para que el LLM pueda hacer joins, agrupaciones y análisis complejos.
- **Generación de Reportes HTML:** Incluye scripts (`generate_report.py` y `generate_report_advanced.py`) para generar dashboards visuales y profesionales en HTML/JS a partir de los datos analizados.
- **Rápido y Ligero:** Construido usando `FastMCP` de Anthropic y `uv` para una gestión rápida del entorno.

## Requisitos Previos

- [uv](https://github.com/astral-sh/uv) instalado.
- Python 3.10 o superior.

## Instalación y Uso

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/rodrigocapiz67-tech/mcp-mef.git
   cd mcp-mef
   ```

2. **Sincronizar el entorno (opcional, uv lo hace automáticamente al ejecutar):**
   ```bash
   uv sync
   ```

3. **Configurar el cliente MCP (Ej. Claude Desktop):**
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
   *(Asegúrate de cambiar `Ruta/Absoluta/A/Este/Repositorio` por la ruta real donde clonaste este proyecto).*

## Herramientas (Tools) Expuestas al LLM

El servidor MCP expone las siguientes herramientas:

* `mef_search_datasets(query)`: Busca datasets relevantes en el portal de datos abiertos del MEF (por ejemplo, al buscar "canon").
* `fetch_mef_dataset(resource_id, table_name, limit)`: Descarga un recurso del portal `datosabiertos.mef.gob.pe` usando su ID y lo inserta como una tabla en la base de datos local SQLite.
* `sql_mef_db(query)`: Ejecuta comandos SQL sobre la base de datos local y retorna los resultados en JSON estructurado para su análisis.

## Generación de Dashboards

El repositorio incluye herramientas adicionales para generar reportes y dashboards a partir de los datos descargados en SQLite (`mef_data.db`):

* `python generate_report.py`: Genera un reporte HTML sencillo con los Tops de recaudación/ingresos (`informe_canon_minero.html`).
* `python generate_report_advanced.py`: Genera un dashboard interactivo avanzado (usando Chart.js) con gráficos de evolución por mes, barras y gráficos de dona mostrando la distribución del canon (`informe_canon_minero_avanzado.html`).

## Advertencia

Los datos obtenidos a través de la API provienen directamente del portal oficial de Datos Abiertos del Gobierno Peruano, pero este proyecto no está afiliado oficialmente al Ministerio de Economía y Finanzas (MEF).
