# MCP-MEF (Perú): CLI + Servidor MCP

Herramienta para interactuar con los datos abiertos del **Ministerio de Economía y Finanzas (MEF)** del Perú, disponible de dos formas que comparten la misma base de datos y lógica:

- **CLI nativo (`mef`):** instalable globalmente, se invoca desde cualquier terminal como cualquier otro comando del sistema.
- **Servidor MCP:** para que un LLM (ej. Claude Desktop) descargue datasets, ejecute SQL y genere informes desde el chat.

Ambos permiten descargar dinámicamente conjuntos de datos desde la API oficial de Datos Abiertos del MEF (CKAN) hacia una base de datos local SQLite, ejecutar consultas SQL nativas para análisis económicos, y generar informes en **Markdown, PDF, Excel y HTML**.

Los datos (`mef_data.db`) y los informes generados (`output/`) se guardan en `~/.mcp-mef` (`%USERPROFILE%\.mcp-mef` en Windows), independientemente de si los generaste con el CLI o desde Claude Desktop.

## Características Principales

- **Búsqueda Integrada:** Busca conjuntos de datos por palabra clave (ej. "gasto", "inversiones") y lista sus recursos año por año.
- **Transparencia Económica:** llega a los datos de la Consulta Amigable (Presupuesto y Ejecución de Gasto e Ingreso, año por año) a través de la API de Datos Abiertos — ver [Transparencia Económica](#transparencia-económica-consulta-amigable).
- **Descarga por streaming:** pagina la API e inserta cada página en SQLite según llega, así que la memoria no crece con el tamaño del dataset (los de gasto anual pasan de 7 millones de filas). Detecta el tipo de cada columna (INTEGER/REAL/TEXT) y conserva los ceros a la izquierda de ubigeos y códigos.
- **A prueba de tablas enormes:** las consultas devuelven como mucho 1000 filas (y avisan si hay más), las exportaciones a CSV/Excel se escriben por lotes con memoria constante, y los gráficos rechazan consultas con más de 2000 puntos en vez de colgarse.
- **Dimensiona antes de bajar:** `mef info <resource_id>` dice cuántas filas y columnas tiene un recurso sin descargarlo.
- **Motor SQL Integrado:** Los datos se guardan en una base de datos `mef_data.db` (SQLite) para que el LLM pueda hacer joins, agrupaciones y análisis complejos.
- **Trazabilidad:** Cada descarga queda registrada (tabla, `resource_id`, fecha, nº de filas) para que los informes puedan citar su fuente automáticamente.
- **Catálogo de datasets:** Guarda alias memorables hacia `resource_id` ya verificados; a partir de ahí `mef fetch` y `mef info` aceptan el alias donde esperan el `resource_id`.
- **Mantenimiento:** `mef paths` dice cuánto ocupa la base y `mef drop <tabla> --vacuum` borra un dataset y devuelve el espacio al disco (un año de gasto son varios GB).
- **Resumen exploratorio (EDA):** Nº de filas, nulos, valores distintos y estadísticas (min/max/promedio) de cualquier tabla descargada.
- **Informes en Markdown, PDF, HTML y Excel:** Cualquier consulta SQL se puede convertir en un informe (tabla + título + fecha + fuente) sin scripts externos.
- **Gráficos:** vía QuickChart (URL online) o generados localmente con matplotlib (PNG, sin depender de internet, ideal para incrustar en PDFs).
- **Consultas acotadas:** las tools de informe, gráfico y exportación sólo ejecutan lectura (`SELECT`/`WITH`), impuesto por el propio motor SQLite, y escriben siempre dentro de `~/.mcp-mef/output`.
- **Probado:** suite de tests que cubre inferencia de tipos, paginación, informes, exportaciones y gráficos sin tocar la red.
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
   Con el CLI ya instalado, basta con apuntar al ejecutable — sin rutas absolutas al repo:
   ```json
   {
     "mcpServers": {
       "mef-siaf": {
         "command": "mef",
         "args": ["mcp"]
       }
     }
   }
   ```
   Si `mef` no está en el PATH que ve Claude Desktop, usa la ruta completa al ejecutable
   (`uv tool dir` te dice dónde quedó) o la forma clásica desde el repo:
   ```json
   { "command": "uv", "args": ["run", "--directory", "Ruta/Absoluta/Al/Repo", "main.py"] }
   ```
   El CLI y el servidor MCP comparten la misma base de datos en `~/.mcp-mef`, así que lo que
   descargues con uno lo puedes consultar con el otro. Para cambiar esa ubicación, define la
   variable de entorno `MCP_MEF_HOME`.

## Uso del CLI

Corre `mef` sin argumentos para ver una portada con el resumen de capacidades y la lista completa
de comandos agrupada por categoría (Búsqueda y Descarga, Consulta y Exploración, Informes y
Gráficos, Catálogo y Exportación). `mef --version` muestra la versión instalada.

```bash
mef search gasto                                             # buscar datasets (una palabra clave)
mef resources presupuesto-y-ejecucion-de-gasto               # recursos del dataset (uno por año)
mef info <resource_id>                                       # filas y columnas, sin descargar
mef fetch <resource_id> gasto_2026 --limit 50000 --page-size 20000
mef schema                                                   # ver tablas disponibles
mef summary gasto_2026                                       # resumen exploratorio (EDA)
mef sql "SELECT * FROM gasto_2026 LIMIT 5"                   # SQL libre (tabla en consola)
mef sql "SELECT ..." --json                                  # el mismo SQL en JSON, para jq
mef report "SELECT ..." "Mi informe" --formats markdown,pdf  # informe en output/
mef export excel "SELECT ..." --filename mi_reporte          # exportar a Excel
mef export csv "SELECT ..." mi_reporte.csv                   # exportar a CSV
mef chart-local "SELECT ..." bar "Mi gráfico"                # PNG local con matplotlib
mef alias add gasto_2026 <resource_id> -d "Gasto mensual 2026"
mef alias list                                               # y `mef alias remove <alias>`
mef fetch gasto_2026 otra_tabla                              # los alias valen como resource_id
mef paths                                                    # rutas, tamaño de la base y nº de filas
mef drop gasto_2026 --vacuum                                 # borra una tabla y recupera el espacio
mef mcp                                                      # arranca el servidor MCP por stdio
```

Los comandos devuelven código de salida 1 cuando fallan, así que se pueden encadenar
(`mef fetch ... && mef report ...`) sin que un error pase desapercibido.

Cada subcomando tiene su propio `--help` (ej. `mef fetch --help`).

## Transparencia Económica (Consulta Amigable)

Los datos que publica el portal de **Transparencia Económica** (`apps5.mineco.gob.pe`, la
Consulta Amigable) están disponibles como datasets en Datos Abiertos, así que esta herramienta
los alcanza sin scrapear el navegador ASPX. El flujo es siempre el mismo:

```bash
mef search gasto                                   # 1. encontrar el dataset -> "slug"
mef resources presupuesto-y-ejecucion-de-gasto      # 2. un resource_id por año
mef info d45f660d-6d14-438e-9d91-300084c9b85f       # 3. cuántas filas tiene (¡son millones!)
mef fetch d45f660d-6d14-438e-9d91-300084c9b85f gasto_2026 --limit 50000 --page-size 20000
```

Para traer el dataset **completo** (millones de filas) en vez de sólo un tramo, usa
`--append` y repite el mismo comando: cada llamada agrega a la tabla y continúa
automáticamente donde se quedó la anterior, hasta que avisa "Descarga completa":

```bash
mef fetch d45f660d-6d14-438e-9d91-300084c9b85f gasto_2026 --append --limit 500000 --page-size 20000
mef fetch d45f660d-6d14-438e-9d91-300084c9b85f gasto_2026 --append --limit 500000 --page-size 20000
# ... repetir hasta "Descarga completa: 'gasto_2026' ya tiene todas las filas disponibles"
```

Sin `--append`, cada `mef fetch` **reemplaza** la tabla entera (incluido `--offset` a mano:
sirve para bajar tramos a tablas *distintas* que luego se unen con `UNION ALL`, no para
completar una misma tabla).

Datasets más usados (el `slug` va en `mef resources`):

| Slug | Contenido |
|---|---|
| `presupuesto-y-ejecucion-de-gasto` | Gasto por año (2009 →), mensual y diario, + diccionario de variables |
| `presupuesto-y-ejecucion-de-ingreso` | Ingresos por año |
| `comparacion-de-presupuesto-ejecucion-gasto` | Comparativos multianuales de gasto |
| `distribucion-geografica-del-gasto` | Gasto por departamento/provincia/distrito |
| `detalle-de-inversiones` | Inversiones del Invierte.pe |

Cosas a tener en cuenta, comprobadas contra la API:

- **Tamaño.** Un año de gasto ronda los **7,7 millones de filas y 63 columnas** (el CSV
  equivalente pesa ~4,6 GB). Bájalo por tramos con `--append` (ver arriba) y filtra ya en
  SQL; el mensaje final te dice cuántas filas quedaron sin traer.
- **Velocidad.** `--page-size 20000` es el máximo y el más eficiente (~20 000 filas cada 7 s);
  con el valor por defecto de 1000 la misma descarga tarda el doble.
- **No hay filtros del lado del servidor.** Los parámetros `filters`, `q` y `fields` de CKAN
  no funcionan en este servidor (se cuelgan o se ignoran), así que el recorte por
  departamento, año o pliego se hace después, con `mef sql`.
- **Diccionario de variables.** Cada dataset trae un recurso `*_Diccionario.csv` (63 filas)
  que explica qué es cada columna; descárgalo a una tabla aparte y consúltalo con SQL.

### Trabajar con tablas de millones de filas

Una vez descargados, los datos son una tabla SQLite normal, pero conviene saber qué hace la
herramienta para no ahogarse (medido sobre una tabla de 1 000 000 de filas):

| Operación | Comportamiento |
|---|---|
| `mef sql` / `sql_mef_db` | Devuelve 1000 filas como máximo y avisa si hay más (`--limit 0` quita el tope). Un `SELECT *` sin tope tardaba 113 s y 1,6 GB de RAM; con el tope son 0,1 s. |
| `mef export csv` | Sin tope: escribe por lotes, con memoria plana (24 MB para un millón de filas). |
| `mef export excel` | Corta en 1 048 575 filas, que es el límite del formato `.xlsx`, y lo avisa. |
| `mef report` | Vuelca `--max-rows` filas (5000 por defecto) y el pie indica si había más. |
| `mef chart` / `chart-local` | Rechaza consultas con más de 2000 puntos: agrupa antes con `GROUP BY`. |
| `mef summary` | Calcula todas las estadísticas en una sola pasada por la tabla. |

Agregar en SQL siempre es más rápido que traerse las filas: un `GROUP BY` sobre un millón de
filas tarda ~1 s, así que no hacen falta índices.

Cuando termines con un año de datos, `mef drop gasto_2009 --vacuum` lo borra y devuelve los GB
al disco; `mef paths` te dice cuánto está ocupando la base en cada momento.

## Herramientas (Tools) Expuestas al LLM vía MCP

El servidor MCP expone las siguientes herramientas (equivalentes 1 a 1 a los subcomandos de `mef`). Todos los archivos que generan (CSV, Excel, PDF, Markdown, HTML, PNG) se guardan en `~/.mcp-mef/output/`.

**Búsqueda y descarga de datos**
* `mef_search_datasets(query, page)`: Busca datasets en el portal por palabra clave y devuelve el `slug` de cada uno, sus formatos y una muestra de recursos. Si una frase no da resultados, reintenta con la palabra más significativa.
* `mef_list_resources(dataset_slug)`: Lista todos los recursos de un dataset con su `resource_id` (los de Transparencia Económica publican uno por año).
* `mef_dataset_info(resource_id)`: Cuántas filas y columnas tiene un recurso, con una fila de muestra, **sin descargarlo**. Conviene llamarlo antes de cualquier `fetch_mef_dataset`.
* `fetch_mef_dataset(resource_id, table_name, limit, page_size, offset, append)`: Descarga un recurso del portal paginando hasta `limit` registros e insertando cada página en SQLite según llega (memoria constante). Sin `append`, la tabla anterior se reemplaza sólo si la descarga termina bien; con `append=True` se agrega a la tabla existente y, si `offset` queda en 0, se autodetecta desde dónde continuar — así se completa un dataset de millones de filas en varias llamadas.
* `mef_register_dataset_alias(alias, resource_id, description)`: Guarda un alias memorable hacia un `resource_id` ya verificado.
* `mef_list_known_datasets()` / `mef_remove_dataset_alias(alias)`: Lista o borra los alias registrados.

**Consulta y exploración**
* `sql_mef_db(query, max_rows)`: Ejecuta comandos SQL sobre la base de datos local y retorna los resultados en JSON estructurado, con un tope de 1000 filas por defecto y un aviso `truncado` cuando hay más. Es la única tool que admite escrituras; las de informe, gráfico y exportación sólo aceptan `SELECT`/`WITH`, y el propio motor SQLite lo impone.
* `mef_get_schema()`: Lista las tablas disponibles, sus columnas, nº de filas y metadata de descarga.
* `mef_dataset_summary(table_name)`: Resumen exploratorio (EDA) de una tabla: nulos, valores distintos, min/max/promedio por columna.

**Mantenimiento**
* `mef_db_stats()`: Tamaño de la base local en disco, tablas y nº de filas de cada una.
* `mef_drop_table(table_name, vacuum)`: Borra una tabla descargada y su trazabilidad; con `vacuum` compacta el archivo. Destructivo: conviene confirmarlo con la persona usuaria.

**Informes y exportación**
* `mef_generate_report(query, title, formats, filename_base, max_rows)`: Genera un informe (tabla + título + fecha + fuente) en `markdown`, `pdf` y/o `html` a partir de cualquier consulta de lectura. La tabla se trunca a `max_rows` filas (5000 por defecto) y el pie indica el total real.
* `mef_export_csv(query, filename)`: Exporta resultados de una consulta a CSV.
* `mef_export_excel(query, filename)`: Exporta resultados de una consulta a un archivo `.xlsx` con encabezados en negrita y columnas autoajustadas.

**Gráficos**
* `mef_generate_chart(query, chart_type, title)`: Genera un gráfico vía QuickChart y retorna una URL (requiere internet para visualizarlo).
* `mef_generate_chart_local(query, chart_type, title, filename)`: Genera un gráfico PNG local con matplotlib, sin depender de servicios externos — ideal para incrustar en informes.

## Ejemplos (legacy)

La carpeta [`examples/`](examples/) conserva dos scripts standalone específicos para la tabla
`canon_minero`, anteriores a `mef report`. Se corren con `uv run python examples/<script>.py`
desde el repo, y requieren haber descargado antes esa tabla.

Para cualquier otra tabla o consulta, usa `mef report` (CLI) o la tool `mef_generate_report`
(MCP) en vez de estos scripts.

## Desarrollo

```bash
uv sync --group dev     # instala dependencias + pytest
uv run pytest -q        # 115 tests, sin tocar la red ni ~/.mcp-mef
```

Los tests usan un `MCP_MEF_HOME` temporal y un transporte HTTP simulado, así que no descargan
nada del portal del MEF ni tocan tus datos reales.

## Advertencia

Los datos obtenidos a través de la API provienen directamente del portal oficial de Datos Abiertos del Gobierno Peruano, pero este proyecto no está afiliado oficialmente al Ministerio de Economía y Finanzas (MEF).
