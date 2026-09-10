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
    ("Transparencia", "Alcanza los datos de Consulta Amigable: presupuesto y ejecución de gasto."),
    ("Descarga por streaming", "Pagina la API e inserta según llega: soporta datasets de millones de filas."),
    ("SQL local", "Motor SQLite embebido: joins, agrupaciones y análisis sobre lo descargado."),
    ("EDA", "Resumen exploratorio de cualquier tabla: nulos, distintos, min/max/promedio."),
    ("Catálogo", "Alias reutilizables hacia resource_id ya verificados."),
    ("Informes", "Markdown, PDF, HTML y Excel a partir de cualquier consulta SQL."),
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
def info(resource_id: str = typer.Argument(..., help="resource_id a inspeccionar.")):
    """Cuántas filas y columnas tiene un recurso, sin descargarlo."""
    _emit(asyncio.run(core.mef_dataset_info(resource_id)))


@app.command("fetch", rich_help_panel="Búsqueda y Descarga")
def fetch(
    resource_id: str = typer.Argument(..., help="resource_id del dataset en datosabiertos.mef.gob.pe."),
    table_name: str = typer.Argument(..., help="Nombre de la tabla local donde guardarlo."),
    limit: int = typer.Option(1000, "--limit", "-l", help="Total de registros a traer (pagina automáticamente)."),
    page_size: int = typer.Option(
        1000, "--page-size", help=f"Filas por petición (máx. {core.MAX_PAGE_SIZE}; más grande = más rápido)."
    ),
    offset: int = typer.Option(0, "--offset", help="Fila desde la que empezar, para traer un dataset por tramos."),
):
    """Descarga un dataset del MEF y lo guarda como tabla SQLite local."""
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

        def _avance(descargadas: int, total: int | None) -> None:
            # El total de la barra es lo que se va a traer de verdad: el mínimo entre lo que
            # queda del dataset y el limit pedido.
            pendiente = max(min(total, offset + limit) - offset, 0) if total else None
            barra.update(tarea, completed=descargadas, total=pendiente or None)

        resultado = asyncio.run(
            core.fetch_mef_dataset(resource_id, table_name, limit, page_size, offset, progress=_avance)
        )
    _emit(resultado)


@app.command("sql", rich_help_panel="Consulta y Exploración")
def sql(
    query: str = typer.Argument(..., help="Consulta SQL a ejecutar sobre mef_data.db."),
    as_json: bool = typer.Option(False, "--json", help="Devuelve JSON crudo, útil para encadenar con jq."),
    limit: int = typer.Option(50, "--limit", "-n", help="Filas a mostrar en la tabla (0 = todas)."),
):
    """Ejecuta SQL nativo sobre la base local y muestra el resultado como tabla (o JSON con --json)."""
    raw = core.sql_mef_db(query)
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
    shown = rows[:limit] if limit > 0 else rows
    table = Table(box=box.SIMPLE_HEAVY, header_style="bold cyan")
    for col in payload["columnas"]:
        table.add_column(str(col), overflow="fold")
    for row in shown:
        table.add_row(*["" if v is None else str(v) for v in row])
    console.print(table)
    suffix = f" (mostrando {len(shown)}; usa --limit 0 para todas)" if len(shown) < len(rows) else ""
    console.print(f"[dim]{len(rows)} fila(s){suffix}[/dim]")


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
    """Muestra dónde viven la base de datos y los archivos generados."""
    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(overflow="fold")
    table.add_row("Base de datos", core.DB_PATH)
    table.add_row("Salidas", core.OUTPUT_DIR)
    table.add_row("Configurable con", "MCP_MEF_HOME")
    console.print(table)


@app.command("mcp", rich_help_panel="Búsqueda y Descarga")
def mcp_serve():
    """Arranca el servidor MCP por stdio (para Claude Desktop y otros clientes MCP)."""
    # Import diferido: arrancar el CLI no debería pagar el coste de cargar el SDK de MCP.
    from .server import run

    run()


if __name__ == "__main__":
    app()
