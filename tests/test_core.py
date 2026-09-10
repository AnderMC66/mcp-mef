"""Tests de la lógica compartida por el CLI y el servidor MCP."""
import json
import os

import pytest

from mcp_mef import core


# --- Helpers de nombres y rutas -------------------------------------------------

@pytest.mark.parametrize("nombre", ["canon minero", "1tabla", "canon;DROP", "_meta_downloads", "sqlite_master"])
def test_nombres_de_tabla_invalidos(nombre):
    with pytest.raises(ValueError):
        core._validate_table_name(nombre)


def test_nombres_de_tabla_validos():
    for nombre in ("canon_minero", "_privada", "T2025"):
        core._validate_table_name(nombre)


def test_quote_ident_escapa_comillas():
    assert core._quote_ident('mal"nombre') == '"mal""nombre"'


def test_output_path_no_escapa_del_directorio(db):
    path = core._output_path("../../secretos", ".csv")
    assert os.path.dirname(os.path.abspath(path)) == os.path.abspath(core.OUTPUT_DIR)


def test_output_path_no_duplica_extension(db):
    assert core._output_path("reporte.csv", ".csv").endswith("reporte.csv")


# --- Inferencia de tipos --------------------------------------------------------

@pytest.mark.parametrize("valores,esperado", [
    (["1", "2", "3"], "INTEGER"),
    (["1.5", "2"], "REAL"),
    (["040101", "150101"], "TEXT"),   # ubigeos: los ceros a la izquierda deben conservarse
    (["nan", "1"], "TEXT"),           # 'nan' es float() válido pero no es un dato numérico
    ([], "TEXT"),
    (["", "abc"], "TEXT"),
])
def test_infer_sql_type(valores, esperado):
    assert core._infer_sql_type(valores) == esperado


def test_ordered_columns_une_todas_las_claves():
    registros = [{"a": 1}, {"b": 2, "a": 3}, {"c": 4}]
    assert core._ordered_columns(registros) == ["a", "b", "c"]


# --- Detección de consultas de lectura ------------------------------------------

@pytest.mark.parametrize("query,esperado", [
    ("SELECT 1", True),
    ("  select * from t", True),
    ("WITH x AS (SELECT 1) SELECT * FROM x", True),
    ("-- comentario\nSELECT 1", True),
    ("/* bloque */ SELECT 1", True),
    ("DELETE FROM canon", False),
    ("DROP TABLE canon", False),
    ("INSERT INTO canon VALUES (1)", False),
])
def test_is_read_query(query, esperado):
    assert core._is_read_query(query) is esperado


def test_consulta_de_solo_lectura_rechaza_escritura(poblada):
    # El authorizer de SQLite debe frenar la escritura aunque el texto empiece por WITH.
    with pytest.raises(Exception):
        core._run_read_query("WITH x AS (SELECT 1) DELETE FROM canon")


# --- sql_mef_db -----------------------------------------------------------------

def test_sql_select(poblada):
    payload = json.loads(core.sql_mef_db("SELECT DEPARTAMENTO FROM canon ORDER BY DEPARTAMENTO"))
    assert payload["columnas"] == ["DEPARTAMENTO"]
    assert payload["filas"][0] == ["Arequipa"]


def test_sql_acepta_cte(poblada):
    """Un `WITH ... SELECT` debe devolver filas, no el mensaje de 'consulta ejecutada'."""
    payload = json.loads(core.sql_mef_db("WITH t AS (SELECT MONTO FROM canon) SELECT COUNT(*) FROM t"))
    assert payload["columnas"] == ["COUNT(*)"]
    assert payload["filas"] == [[4]]


def test_sql_error_devuelve_status_error(poblada):
    payload = json.loads(core.sql_mef_db("SELECT * FROM no_existe"))
    assert payload["status"] == "error"


def test_sql_escritura_se_confirma(poblada):
    core.sql_mef_db("DELETE FROM canon WHERE DEPARTAMENTO = 'Cusco'")
    payload = json.loads(core.sql_mef_db("SELECT COUNT(*) FROM canon"))
    assert payload["filas"] == [[3]]


# --- Esquema y resumen ----------------------------------------------------------

def test_schema_lista_tablas_y_oculta_metadata(poblada):
    core.mef_register_dataset_alias("canon_2025", "abc-123")
    schema = json.loads(core.mef_get_schema())
    assert "canon" in schema
    assert schema["canon"]["filas"] == 4
    assert not any(t.startswith("_meta") for t in schema)


def test_schema_vacio_da_mensaje_util(db):
    assert "vacía" in core.mef_get_schema()


def test_summary(poblada):
    resumen = json.loads(core.mef_dataset_summary("canon"))
    assert resumen["total_filas"] == 4
    monto = resumen["columnas"]["MONTO"]
    assert monto["nulos"] == 1
    assert monto["max"] == 1500.5
    assert resumen["columnas"]["DEPARTAMENTO"]["valores_distintos"] == 3


def test_summary_tabla_inexistente(db):
    assert "no existe" in core.mef_dataset_summary("fantasma")


# --- Catálogo -------------------------------------------------------------------

def test_alias_se_registra_y_actualiza(db):
    core.mef_register_dataset_alias("canon", "id-1", "primero")
    core.mef_register_dataset_alias("canon", "id-2", "segundo")
    catalogo = json.loads(core.mef_list_known_datasets())
    assert len(catalogo) == 1
    assert catalogo[0]["resource_id"] == "id-2"


def test_alias_vacio_es_error(db):
    assert core.mef_register_dataset_alias("  ", "id").startswith("Error")


# --- Informes y exportaciones ---------------------------------------------------

def test_report_genera_los_tres_formatos(poblada):
    salida = core.mef_generate_report(
        "SELECT * FROM canon", "Canon 2025", ["markdown", "html", "pdf"], "canon_test"
    )
    for ext in (".md", ".html", ".pdf"):
        assert os.path.exists(os.path.join(core.OUTPUT_DIR, f"canon_test{ext}"))
    assert "Informe generado" in salida


def test_report_rechaza_escritura(poblada):
    assert core.mef_generate_report("DELETE FROM canon", "x").startswith("Error")


def test_report_trunca_y_avisa(poblada):
    salida = core.mef_generate_report("SELECT * FROM canon", "Canon", ["markdown"], "trunc", max_rows=2)
    contenido = open(os.path.join(core.OUTPUT_DIR, "trunc.md"), encoding="utf-8").read()
    assert "Filas mostradas: 2" in contenido
    assert "la consulta devuelve más" in contenido
    assert "2 filas" in salida and "devuelve más" in salida


def test_report_completo_dice_el_total(poblada):
    core.mef_generate_report("SELECT * FROM canon", "Canon", ["markdown"], "full")
    contenido = open(os.path.join(core.OUTPUT_DIR, "full.md"), encoding="utf-8").read()
    assert "Total de filas: 4" in contenido
    assert "devuelve más" not in contenido


def test_report_escapa_pipes_en_markdown(poblada):
    core.sql_mef_db("UPDATE canon SET DEPARTAMENTO = 'a|b' WHERE DEPARTAMENTO = 'Cusco'")
    core.mef_generate_report("SELECT DEPARTAMENTO FROM canon", "Pipes", ["markdown"], "pipes")
    contenido = open(os.path.join(core.OUTPUT_DIR, "pipes.md"), encoding="utf-8").read()
    assert "a\\|b" in contenido


def test_report_formato_desconocido(poblada):
    assert "no reconocido" in core.mef_generate_report("SELECT 1", "x", ["docx"])


def test_export_csv(poblada):
    salida = core.mef_export_csv("SELECT DEPARTAMENTO, MONTO FROM canon", "datos")
    ruta = os.path.join(core.OUTPUT_DIR, "datos.csv")
    assert os.path.exists(ruta)
    assert "4 filas" in salida
    assert open(ruta, encoding="utf-8-sig").read().startswith("DEPARTAMENTO,MONTO")


def test_export_csv_no_escapa_del_directorio(poblada):
    core.mef_export_csv("SELECT 1", "../../fuera.csv")
    assert os.path.exists(os.path.join(core.OUTPUT_DIR, "fuera.csv"))


def test_export_csv_rechaza_escritura(poblada):
    assert core.mef_export_csv("DROP TABLE canon", "x").startswith("Error")


def test_export_excel(poblada):
    core.mef_export_excel("SELECT * FROM canon", "libro")
    assert os.path.exists(os.path.join(core.OUTPUT_DIR, "libro.xlsx"))


# --- Gráficos -------------------------------------------------------------------

def test_chart_local(poblada):
    salida = core.mef_generate_chart_local(
        "SELECT DEPARTAMENTO, SUM(MONTO) FROM canon GROUP BY DEPARTAMENTO", "bar", "Por departamento"
    )
    assert salida.startswith("Gráfico generado:")
    assert os.path.exists(os.path.join(core.OUTPUT_DIR, "por_departamento.png"))


def test_chart_tipo_invalido(poblada):
    assert core.mef_generate_chart_local("SELECT 1, 2", "donut", "x").startswith("chart_type")


def test_chart_segunda_columna_no_numerica(poblada):
    salida = core.mef_generate_chart_local("SELECT UBIGEO, DEPARTAMENTO FROM canon", "bar", "x")
    assert "numérica" in salida


def test_chart_omite_valores_nulos(poblada):
    """Un GROUP BY con una categoría sin datos no debe tumbar el gráfico entero."""
    salida = core.mef_generate_chart_local(
        "SELECT DEPARTAMENTO, SUM(MONTO) FROM canon GROUP BY DEPARTAMENTO", "bar", "Nulos"
    )
    assert "1 fila(s) con valor NULL omitidas" in salida


def test_chart_todo_nulo(poblada):
    salida = core.mef_generate_chart_local("SELECT DEPARTAMENTO, NULL FROM canon", "bar", "x")
    assert "NULL" in salida


def test_chart_una_sola_columna(poblada):
    assert "2 columnas" in core.mef_generate_chart_local("SELECT DEPARTAMENTO FROM canon", "bar", "x")


def test_chart_quickchart_url(poblada):
    salida = core.mef_generate_chart(
        "SELECT DEPARTAMENTO, SUM(MONTO) FROM canon GROUP BY DEPARTAMENTO", "bar", "Título"
    )
    assert "quickchart.io/chart?c=" in salida
