"""Aísla cada test en su propio ~/.mcp-mef temporal.

core.py resuelve APP_DIR al importarse, así que la variable de entorno tiene que estar puesta
antes del primer import: por eso se apunta a un directorio temporal aquí, en conftest.
"""
import os
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="mcp-mef-tests-")
os.environ["MCP_MEF_HOME"] = _TMP_HOME

import pytest  # noqa: E402

from mcp_mef import core  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Base de datos y carpeta de salida limpias para cada test."""
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "mef_data.db"))
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setattr(core, "OUTPUT_DIR", str(out))
    return core


@pytest.fixture()
def poblada(db):
    """Una tabla `canon` con datos suficientes para consultar, graficar y exportar."""
    with db._db() as conn:
        conn.execute('CREATE TABLE canon (DEPARTAMENTO TEXT, UBIGEO TEXT, MONTO REAL)')
        conn.executemany(
            'INSERT INTO canon VALUES (?, ?, ?)',
            [("Arequipa", "040101", 1500.5), ("Cusco", "080101", 900.0),
             ("Puno", "210101", None), ("Arequipa", "040102", 250.25)],
        )
        conn.commit()
    return db
