"""Ciclo de vida de los datos locales: estadísticas, borrado y compactación."""
import json
import os

import pytest

from mcp_mef import core


def test_db_stats(poblada):
    stats = json.loads(core.mef_db_stats())
    assert stats["tablas"] == {"canon": 4}
    assert stats["filas_totales"] == 4
    assert stats["tamano_mb"] >= 0
    assert stats["tamano"].endswith(("B", "KB", "MB", "GB"))
    assert stats["base_de_datos"] == core.DB_PATH


def test_db_stats_base_vacia(db):
    stats = json.loads(core.mef_db_stats())
    assert stats["tablas"] == {}
    assert stats["filas_totales"] == 0


def test_drop_table(poblada):
    salida = core.mef_drop_table("canon")
    assert "4 filas" in salida
    assert json.loads(core.mef_db_stats())["tablas"] == {}


def test_drop_table_limpia_la_trazabilidad(poblada, monkeypatch):
    with core._db() as conn:
        core._register_download(conn.cursor(), "canon", "uuid-1", 4)
        conn.commit()
    core.mef_drop_table("canon")
    with core._db() as conn:
        resto = conn.execute("SELECT COUNT(*) FROM _meta_downloads WHERE table_name='canon'").fetchone()
    assert resto[0] == 0


def test_drop_table_inexistente(db):
    assert "no existe" in core.mef_drop_table("fantasma")


@pytest.mark.parametrize("nombre", ["_meta_downloads", "sqlite_master", "tabla mala"])
def test_drop_table_protege_los_nombres_reservados(poblada, nombre):
    assert core.mef_drop_table(nombre).startswith("Error")


def test_drop_con_vacuum_recupera_espacio(db):
    """SQLite no encoge el archivo al borrar: sólo VACUUM devuelve el espacio."""
    with core._db() as conn:
        conn.execute("CREATE TABLE pesada (relleno TEXT)")
        conn.executemany(
            "INSERT INTO pesada VALUES (?)", [("x" * 500,) for _ in range(20000)]
        )
        conn.commit()
    grande = os.path.getsize(core.DB_PATH)

    salida = core.mef_drop_table("pesada", vacuum=True)
    assert "La base pasó de" in salida
    assert os.path.getsize(core.DB_PATH) < grande / 2


def test_drop_sin_vacuum_avisa(poblada):
    assert "vacuum=True" in core.mef_drop_table("canon")


def test_excel_corta_en_el_limite_del_formato(poblada, monkeypatch):
    """El tope real son 1 048 575 filas; aquí se simula para cubrir la rama."""
    monkeypatch.setattr(core, "EXCEL_MAX_ROWS", 2)
    salida = core.mef_export_excel("SELECT DEPARTAMENTO FROM canon", "tope")
    assert "2 filas" in salida
    assert "no admite más de 2 filas" in salida
    assert "mef_export_csv" in salida
