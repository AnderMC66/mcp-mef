"""CLI nativo del MCP-MEF: `mef <comando>` desde cualquier terminal.

Usa la misma lógica que el servidor MCP (mcp_mef.core), así que comparte los mismos datos
(~/.mcp-mef/mef_data.db) sin importar si se invoca desde aquí o desde Claude Desktop.
"""
import asyncio
import json
import sys

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from . import __version__, core

# Algunas consolas de Windows (cp1252/cp850, o salida redirigida a archivo) no
# soportan todos los caracteres Unicode. En vez de crashear con UnicodeEncodeError,
# los reemplaza por '?' y sigue funcionando.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

AUTHOR = "andermc66"
console = Console()


def _emit(result: str) -> None:
    """Imprime el resultado y sale con código 1 si la operación falló.

    Sin esto, `mef fetch ... && algo-mas` seguía encadenando aunque la descarga hubiera
    fallado: el error se veía en pantalla pero el proceso terminaba con éxito.
    """
    console.print(result, markup=False, highlight=False, soft_wrap=True)
    if result.lstrip().lower().startswith(("error", "excepción", "excepcion")):
        raise typer.Exit(code=1)


_CAPABILITIES = [
    ("Búsqueda", "Encuentra datasets del MEF por palabra clave y lista sus recursos por año."),
    ("Consulta Amigable", "Extrae datos en tiempo real por ministerio y fechas (apps5.mineco.gob.pe)."),
    ("Búsqueda Vectorial / FTS5", "Búsqueda semántica con similitud coseno y texto completo BM25."),
    ("Descarga por streaming", "Pagina la API e inserta según llega: soporta datasets de millones de filas."),
    ("SQL local", "Motor SQLite embebido: joins, agrupaciones y análisis sobre lo descargado."),
    ("EDA", "Resumen exploratorio de cualquier tabla: nulos, distintos, min/max/promedio."),
    ("Catálogo", "Alias reutilizables hacia resource_id ya verificados."),
    ("Informes y Excel", "Markdown, PDF, HTML y Excel (.xlsx) estilizado a partir de cualquier consulta."),
    ("Gráficos", "Vía QuickChart (online) o localmente con matplotlib (PNG offline)."),
]

app = typer.Typer(
    name="mef",
    help=f"[bold]MEF-CLI[/bold] · Datos Abiertos del MEF (Perú) — descarga, SQL e informes. [dim]por {AUTHOR}[/dim]",
    epilog=f"Desarrollado por [bold]{AUTHOR}[/bold] · v{__version__}",
    rich_markup_mode="rich",
    no_args_is_help=False,
)

alias_app = typer.Typer(help="Gestiona el catálogo de datasets registrados (alias -> resource_id).")
export_app = typer.Typer(help="Exporta el resultado de una consulta SQL a un archivo.")
app.add_typer(alias_app, name="alias", rich_help_panel="Catálogo y Exportación")
app.add_typer(export_app, name="export", rich_help_panel="Catálogo y Exportación")


def _print_banner() -> None:
    console.print()
    console.print(
        Panel.fit(
            f"[bold bright_white]MEF[/bold bright_white][bold cyan]-CLI[/bold cyan]\n"
            f"[dim]Datos Abiertos del MEF (Perú) · descarga, SQL e informes[/dim]\n"
            f"[dim]v{__version__} · por [bold]{AUTHOR}[/bold][/dim]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 4),
        )
    )
    console.print()
    caps = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
    caps.add_column(style="bold cyan")
    caps.add_column()
    for name, desc in _CAPABILITIES:
        caps.add_row(f"- {name}", desc)
    console.print(caps)
    console.print()


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Muestra la versión y sale."),
):
    """MEF-CLI: descarga datos del MEF, corre SQL y genera informes, todo desde la terminal."""
    if version:
        console.print(f"MEF-CLI v{__version__} · por {AUTHOR}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        _print_banner()
        console.print(ctx.get_help())
        raise typer.Exit()


@app.command("search", rich_help_panel="Búsqueda y Descarga")
def search(
    query: str = typer.Argument(..., help="Palabra clave a buscar, ej. 'gasto' o 'inversiones'."),
    page: int = typer.Option(1, "--page", "-p", help="Página de resultados."),
):
    """Busca datasets en el portal de Datos Abiertos del MEF."""
    _emit(asyncio.run(core.mef_search_datasets(query, page)))


@app.command("resources", rich_help_panel="Búsqueda y Descarga")
def resources(
    slug: str = typer.Argument(..., help="Slug del dataset, ej. 'presupuesto-y-ejecucion-de-gasto'."),
):
    """Lista los recursos de un dataset (uno por año en los de Transparencia Económica)."""
    _emit(asyncio.run(core.mef_list_resources(slug)))


@app.command("info", rich_help_panel="Búsqueda y Descarga")
def info(resource_id: str = typer.Argument(..., help="resource_id (o alias) a inspeccionar.")):
    """Cuántas filas y columnas tiene un recurso, sin descargarlo."""
    _emit(asyncio.run(core.mef_dataset_info(resource_id)))


@app.command("fetch", rich_help_panel="Búsqueda y Descarga")
def fetch(
    resource_id: str = typer.Argument(..., help="resource_id del recurso, o un alias registrado."),
    table_name: str = typer.Argument(..., help="Nombre de la tabla local donde guardarlo."),
    limit: int = typer.Option(1000, "--limit", "-l", help="Total de registros a traer (pagina automáticamente)."),
    page_size: int = typer.Option(
        1000, "--page-size", help=f"Filas por petición (máx. {core.MAX_PAGE_SIZE}; más grande = más rápido)."
    ),
    offset: int = typer.Option(
        0, "--offset", help="Fila desde la que empezar. Con --append y 0, se autodetecta."
    ),
    append: bool = typer.Option(
        False, "--append",
        help="Agrega a table_name en vez de reemplazarla: repite el comando para traer el dataset completo por tramos.",
    ),
):
    """Descarga un dataset del MEF y lo guarda como tabla SQLite local.

    Para un dataset de millones de filas, usa --append y repite el mismo comando: cada
    llamada continúa exactamente donde se quedó la anterior, hasta agotar el dataset.

        mef fetch <resource_id> gasto_2026 --append --limit 500000
        mef fetch <resource_id> gasto_2026 --append --limit 500000   # continúa solo
        ...  # repetir hasta que diga "Descarga completa"
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]Descargando[/cyan]"),
        BarColumn(),
        TextColumn("{task.completed:,} filas"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as barra:
        # total=None deja la barra en modo indeterminado hasta que la API informa el total.
        tarea = barra.add_task("fetch", total=None)

        # Con --append y offset=0, el punto de partida real lo decide fetch_mef_dataset
        # (autodetectado a partir de las filas que la tabla ya tiene), no el offset=0 de acá:
        # en ese caso el techo de la barra sólo puede acotarse por --limit.
        autoresume = append and offset == 0

        def _avance(descargadas: int, total: int | None) -> None:
            techo = limit
            if total is not None and not autoresume:
                techo = max(min(total, offset + limit) - offset, 0)
            barra.update(tarea, completed=descargadas, total=techo or None)

        resultado = asyncio.run(
            core.fetch_mef_dataset(
                resource_id, table_name, limit, page_size, offset, progress=_avance, append=append
            )
        )
    _emit(resultado)


@app.command("sql", rich_help_panel="Consulta y Exploración")
def sql(
    query: str = typer.Argument(..., help="Consulta SQL a ejecutar sobre mef_data.db."),
    as_json: bool = typer.Option(False, "--json", help="Devuelve JSON crudo, útil para encadenar con jq."),
    limit: int = typer.Option(
        core.MAX_SQL_ROWS, "--limit", "-n", help="Filas a traer (0 = todas; ojo con tablas de millones)."
    ),
):
    """Ejecuta SQL nativo sobre la base local y muestra el resultado como tabla (o JSON con --json)."""
    raw = core.sql_mef_db(query, limit)
    if as_json:
        console.print(raw, markup=False, highlight=False, soft_wrap=True)
        raise typer.Exit(code=1 if '"status": "error"' in raw else 0)

    payload = json.loads(raw)
    if payload.get("status") == "error":
        console.print(f"[red]Error SQL:[/red] {payload['message']}")
        raise typer.Exit(code=1)
    if "columnas" not in payload:
        console.print(payload.get("message", "OK"))
        return

    rows = payload["filas"]
    table = Table(box=box.SIMPLE_HEAVY, header_style="bold cyan")
    for col in payload["columnas"]:
        table.add_column(str(col), overflow="fold")
    for row in rows:
        table.add_row(*["" if v is None else str(v) for v in row])
    console.print(table)
    suffix = " [yellow](hay más filas: usa --limit 0, GROUP BY o export)[/yellow]" if payload.get("truncado") else ""
    console.print(f"[dim]{len(rows)} fila(s)[/dim]{suffix}")


@app.command("schema", rich_help_panel="Consulta y Exploración")
def schema():
    """Lista las tablas disponibles, sus columnas, filas y metadata de descarga."""
    _emit(core.mef_get_schema())


@app.command("summary", rich_help_panel="Consulta y Exploración")
def summary(table_name: str = typer.Argument(..., help="Tabla a resumir.")):
    """Resumen exploratorio (EDA) de una tabla: nulos, distintos, min/max/promedio."""
    _emit(core.mef_dataset_summary(table_name))


@app.command("report", rich_help_panel="Informes y Gráficos")
def report(
    query: str = typer.Argument(..., help="Consulta SQL SELECT a convertir en informe."),
    title: str = typer.Argument(..., help="Título del informe."),
    formats: str = typer.Option("markdown", "--formats", "-f", help="Lista separada por comas: markdown,pdf,html"),
    filename: str = typer.Option("", "--filename", help="Nombre base del archivo (por defecto, deriva del título)."),
    max_rows: int = typer.Option(
        core.MAX_REPORT_ROWS, "--max-rows", help="Máximo de filas volcadas al informe (0 = sin tope)."
    ),
):
    """Genera un informe (Markdown/PDF/HTML) a partir de una consulta SQL."""
    fmt_list = [f.strip() for f in formats.split(",") if f.strip()]
    _emit(core.mef_generate_report(query, title, fmt_list, filename, max_rows))


@app.command("chart", rich_help_panel="Informes y Gráficos")
def chart(
    query: str = typer.Argument(..., help="Consulta SQL: 2 columnas, etiqueta y valor numérico."),
    chart_type: str = typer.Argument(..., help="'bar', 'pie' o 'line'."),
    title: str = typer.Argument(..., help="Título del gráfico."),
):
    """Genera un gráfico vía QuickChart y retorna una URL (requiere internet)."""
    _emit(core.mef_generate_chart(query, chart_type, title))


@app.command("chart-local", rich_help_panel="Informes y Gráficos")
def chart_local(
    query: str = typer.Argument(..., help="Consulta SQL: 2 columnas, etiqueta y valor numérico."),
    chart_type: str = typer.Argument(..., help="'bar', 'pie' o 'line'."),
    title: str = typer.Argument(..., help="Título del gráfico."),
    filename: str = typer.Option("", "--filename", help="Nombre base del PNG (por defecto, deriva del título)."),
):
    """Genera un gráfico PNG local con matplotlib, sin depender de servicios externos."""
    _emit(core.mef_generate_chart_local(query, chart_type, title, filename))


@alias_app.command("add")
def alias_add(
    alias: str = typer.Argument(..., help="Alias memorable, ej. 'canon_minero_2025'."),
    resource_id: str = typer.Argument(..., help="resource_id verificado a asociar."),
    description: str = typer.Option("", "--description", "-d", help="Descripción opcional."),
):
    """Registra un alias hacia un resource_id ya verificado."""
    _emit(core.mef_register_dataset_alias(alias, resource_id, description))


@alias_app.command("remove")
def alias_remove(alias: str = typer.Argument(..., help="Alias a borrar del catálogo.")):
    """Borra un alias registrado."""
    _emit(core.mef_remove_dataset_alias(alias))


@alias_app.command("list")
def alias_list():
    """Lista los datasets registrados previamente."""
    _emit(core.mef_list_known_datasets())


@export_app.command("csv")
def export_csv(
    query: str = typer.Argument(..., help="Consulta SQL a exportar."),
    filename: str = typer.Argument(..., help="Nombre del archivo .csv de salida."),
):
    """Exporta el resultado de una consulta a CSV."""
    _emit(core.mef_export_csv(query, filename))


@export_app.command("excel")
def export_excel(
    query: str = typer.Argument(..., help="Consulta SQL SELECT a exportar."),
    filename: str = typer.Option("", "--filename", help="Nombre base del .xlsx (por defecto 'reporte')."),
):
    """Exporta el resultado de una consulta a Excel (.xlsx)."""
    _emit(core.mef_export_excel(query, filename))


@app.command("paths", rich_help_panel="Consulta y Exploración")
def paths():
    """Muestra dónde viven la base y las salidas, y cuánto ocupan."""
    stats = json.loads(core.mef_db_stats())
    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(overflow="fold")
    table.add_row("Base de datos", f"{core.DB_PATH}  [dim]({stats['tamano']})[/dim]")
    table.add_row("Salidas", core.OUTPUT_DIR)
    table.add_row("Tablas", f"{len(stats['tablas'])} ({stats['filas_totales']:,} filas)")
    table.add_row("Configurable con", "MCP_MEF_HOME")
    console.print(table)


@app.command("drop", rich_help_panel="Consulta y Exploración")
def drop(
    table_name: str = typer.Argument(..., help="Tabla a borrar."),
    vacuum: bool = typer.Option(False, "--vacuum", help="Compacta la base para recuperar el espacio."),
    yes: bool = typer.Option(False, "--yes", "-y", help="No pedir confirmación."),
):
    """Borra una tabla descargada (destructivo)."""
    if not yes:
        typer.confirm(f"¿Borrar la tabla '{table_name}'? Volver a descargarla puede tardar", abort=True)
    _emit(core.mef_drop_table(table_name, vacuum))


@app.command("amigable", rich_help_panel="Consulta y Exploración")
def amigable_cmd(
    anio: int = typer.Option(2024, "--anio", "-y", help="Año fiscal (ej. 2024, 2025, 2026)."),
    ministerio: str = typer.Option("", "--ministerio", "-m", help="Ministerio o sector (ej. SALUD, EDUCACION, 11, MTC)."),
    mes: int = typer.Option(None, "--mes", help="Mes de ejecución (1 a 12)."),
    excel: bool = typer.Option(False, "--excel", help="Exporta directamente a Excel (.xlsx)."),
    filename: str = typer.Option("", "--filename", help="Nombre personalizado para el archivo Excel."),
    tipo: str = typer.Option("mensual", "--tipo", "-t", help="Tipo de consulta: 'mensual' o 'diaria'."),
):
    """Consulta en tiempo real el portal oficial de Consulta Amigable (apps5.mineco.gob.pe)."""
    from . import consulta_amigable

    async def _run():
        return await consulta_amigable.consultar_amigable(
            anio=anio,
            ministerio=ministerio,
            mes=mes,
            export_excel=excel,
            nombre_excel=filename,
            tipo=tipo,
        )

    res = asyncio.run(_run())
    if "error" in res:
        console.print(f"[red]{res['error']}[/red]")
        raise typer.Exit(code=1)

    datos = res.get("datos", [])
    sub_info = f" · Corte: {res.get('fecha_actualizacion')}" if res.get('fecha_actualizacion') else ""
    table = Table(title=f"MEF Consulta Amigable ({res.get('modulo', 'mensual')}) · {res.get('ministerio')} ({res.get('anio')}){sub_info}", box=box.ROUNDED)
    table.add_column("Descripción", style="cyan", no_wrap=False)
    table.add_column("PIM (S/)", justify="right")
    table.add_column("Devengado (S/)", justify="right", style="green")
    table.add_column("Girado (S/)", justify="right")
    table.add_column("% Avance", justify="right", style="bold yellow")

    for d in datos[:30]:
        pim = f"{d.get('pim', 0):,.2f}" if d.get('pim') is not None else "-"
        dev = f"{d.get('devengado', 0):,.2f}" if d.get('devengado') is not None else "-"
        gir = f"{d.get('girado', 0):,.2f}" if d.get('girado') is not None else "-"
        av = f"{d.get('avance_porcentaje', 0):.1f}%" if d.get('avance_porcentaje') is not None else "-"
        table.add_row(d.get("descripcion", ""), pim, dev, gir, av)

    console.print(table)
    if len(datos) > 30:
        console.print(f"[dim]Mostrando 30 de {len(datos)} registros.[/dim]")
    if "archivo_excel" in res:
        console.print(f"[bold green]Excel generado:[/bold green] {res['archivo_excel']}")


@app.command("pliegos", rich_help_panel="Consulta y Exploración")
def pliegos_cmd(
    ministerio: str = typer.Argument(..., help="Ministerio o sector (ej. SALUD, EDUCACION, 11)."),
    anio: int = typer.Option(2024, "--anio", "-y", help="Año fiscal (ej. 2024, 2025)."),
    excel: bool = typer.Option(False, "--excel", help="Exporta directamente a Excel (.xlsx)."),
    filename: str = typer.Option("", "--filename", help="Nombre del archivo Excel."),
):
    """Lista los pliegos y organismos de un ministerio en tiempo real desde Consulta Amigable."""
    from . import consulta_amigable

    async def _run():
        return await consulta_amigable.consultar_amigable_pliegos(
            anio=anio,
            ministerio=ministerio,
            export_excel=excel,
            nombre_excel=filename,
        )

    res = asyncio.run(_run())
    if "error" in res:
        console.print(f"[red]{res['error']}[/red]")
        raise typer.Exit(code=1)

    pliegos = res.get("pliegos", [])
    table = Table(title=f"Pliegos Ejecutores · {res.get('sector')} ({res.get('anio')})", box=box.ROUNDED)
    table.add_column("Pliego", style="cyan")
    table.add_column("PIM (S/)", justify="right")
    table.add_column("Devengado (S/)", justify="right", style="green")
    table.add_column("% Avance", justify="right", style="bold yellow")

    for p in pliegos:
        pim = f"{p.get('pim', 0):,.2f}" if p.get('pim') is not None else "-"
        dev = f"{p.get('devengado', 0):,.2f}" if p.get('devengado') is not None else "-"
        av = f"{p.get('avance_porcentaje', 0):.1f}%" if p.get('avance_porcentaje') is not None else "-"
        table.add_row(p.get("descripcion", ""), pim, dev, av)

    console.print(table)
    if "archivo_excel" in res:
        console.print(f"[bold green]Excel generado:[/bold green] {res['archivo_excel']}")


@app.command("fts", rich_help_panel="Consulta y Exploración")
def fts_search_cmd(
    query: str = typer.Argument(..., help="Texto o palabras a buscar (ej. 'hospital huancavelica')."),
    table: str = typer.Argument(..., help="Tabla donde buscar (ej. gasto_2026)."),
    limit: int = typer.Option(20, "--limit", "-l", help="Máximo número de coincidencias."),
):
    """Búsqueda rápida de texto completo con SQLite FTS5 y ponderación BM25."""
    from . import search as search_mod

    _emit(search_mod.mef_fts_search(query=query, table_name=table, limit=limit))


@app.command("vector", rich_help_panel="Consulta y Exploración")
def vector_search_cmd(
    query: str = typer.Argument(..., help="Texto o concepto a buscar semánticamente."),
    table: str = typer.Argument(..., help="Tabla donde buscar (ej. gasto_2026)."),
    field: str = typer.Option("", "--field", "-f", help="Columna textual a vectorizar."),
    top_k: int = typer.Option(10, "--top-k", "-k", help="Cantidad de resultados más similares."),
):
    """Búsqueda por similitud vectorial y semántica (embeddings n-gram + coseno con numpy)."""
    from . import search as search_mod

    _emit(search_mod.mef_vector_search(query=query, table_name=table, field=field, top_k=top_k))


@app.command("index", rich_help_panel="Consulta y Exploración")
def create_index_cmd(
    table: str = typer.Argument(..., help="Tabla a indexar."),
):
    """Crea un índice FTS5 sobre las columnas textuales de una tabla para búsqueda ultrarrápida."""
    from . import search as search_mod

    _emit(search_mod.mef_create_search_index(table_name=table))


@app.command("mcp", rich_help_panel="Búsqueda y Descarga")
def mcp_serve():
    """Arranca el servidor MCP por stdio (para Claude Desktop y otros clientes MCP)."""
    from .server import run

    run()


if __name__ == "__main__":
    app()
