import json
import sqlite3
import pytest

from mcp_mef import consulta_amigable, search, core


def test_resolver_sector():
    cod, nombre = consulta_amigable.resolver_sector("11")
    assert cod == "11"
    assert "SALUD" in nombre

    cod, nombre = consulta_amigable.resolver_sector("salud")
    assert cod == "11"
    assert "SALUD" in nombre

    cod, nombre = consulta_amigable.resolver_sector("MTC")
    assert cod == "36"

    cod, nombre = consulta_amigable.resolver_sector("MINEDU")
    assert cod == "10"


def test_exportar_filas_a_excel(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "OUTPUT_DIR", str(tmp_path))
    datos = [
        {
            "descripcion": "011: M. DE SALUD",
            "pia": 1000.0,
            "pim": 1200.0,
            "certificacion": 1100.0,
            "compromiso_anual": 1050.0,
            "compromiso_mensual": 1000.0,
            "devengado": 950.0,
            "girado": 900.0,
            "avance_porcentaje": 79.2
        }
    ]
    archivo = consulta_amigable.exportar_filas_a_excel(datos, "Test Report", "test_report")
    assert archivo.endswith(".xlsx")
    assert tmp_path.joinpath("test_report.xlsx").exists()


def test_fts_and_vector_search(tmp_path, monkeypatch):
    db_file = tmp_path / "test_mef.db"
    monkeypatch.setattr(core, "DB_PATH", str(db_file))

    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("""
            CREATE TABLE obras (
                id INTEGER PRIMARY KEY,
                PRODUCTO_PROYECTO_NOMBRE TEXT,
                SECTOR_NOMBRE TEXT,
                MONTO_PIM REAL
            )
        """)
        conn.execute("""
            INSERT INTO obras (PRODUCTO_PROYECTO_NOMBRE, SECTOR_NOMBRE, MONTO_PIM) VALUES
            ('CONSTRUCCION DEL CENTRO DE SALUD EN CHORRILLOS', 'SALUD', 500000.0),
            ('MEJORAMIENTO DE LA INFRAESTRUCTURA VIAL EN CUSCO', 'TRANSPORTES', 1200000.0),
            ('ADQUISICION DE EQUIPAMIENTO MEDICO PARA HOSPITAL', 'SALUD', 350000.0)
        """)

    # Test FTS5 creation and search
    idx_res = json.loads(search.mef_create_search_index("obras"))
    assert idx_res["filas_indexadas"] == 3

    fts_res = json.loads(search.mef_fts_search("hospital", "obras", limit=5))
    assert fts_res["total_encontrados"] >= 1
    assert "HOSPITAL" in fts_res["coincidencias"][0]["PRODUCTO_PROYECTO_NOMBRE"]

    # Test Vector similarity search
    vec_res = json.loads(search.mef_vector_search("centro salud chorrillos", "obras", field="PRODUCTO_PROYECTO_NOMBRE", top_k=2))
    assert vec_res["total_coincidencias"] >= 1
    assert "CHORRILLOS" in vec_res["coincidencias"][0]["PRODUCTO_PROYECTO_NOMBRE"]
    assert vec_res["coincidencias"][0]["_similitud_vectorial"] > 0.0
