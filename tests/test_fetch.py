"""Tests de la descarga desde la API del MEF, con el transporte HTTP simulado."""
import asyncio
import json

import httpx
import pytest

from mcp_mef import core

# La clase real, capturada antes de cualquier monkeypatch: si se leyera dentro del helper,
# el segundo parcheo de un mismo test envolvería al primero en vez de reemplazarlo.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _fake_client(paginas, monkeypatch, total=None):
    """Sustituye la red por una lista de páginas de registros predefinidas."""
    llamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        offset = int(request.url.params.get("offset", 0))
        pagina = paginas[len(llamadas) - 1] if len(llamadas) <= len(paginas) else []
        cuerpo = {"records": pagina, "result": {"include_total": str(total)} if total else {}}
        return httpx.Response(200, json=cuerpo)

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _REAL_ASYNC_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return llamadas


def test_fetch_guarda_y_tipa(db, monkeypatch):
    _fake_client([[
        {"DEPARTAMENTO": "Arequipa", "UBIGEO": "040101", "MONTO": "1500.5", "ANIO": "2025"},
        {"DEPARTAMENTO": "Cusco", "UBIGEO": "080101", "MONTO": "900", "ANIO": "2025"},
    ]], monkeypatch)

    salida = asyncio.run(core.fetch_mef_dataset("res-1", "canon", limit=10))
    assert "2 registros" in salida
    assert "UBIGEO:TEXT" in salida      # el ubigeo conserva su cero inicial
    assert "MONTO:REAL" in salida
    assert "ANIO:INTEGER" in salida

    payload = json.loads(core.sql_mef_db("SELECT UBIGEO FROM canon ORDER BY UBIGEO"))
    assert payload["filas"][0] == ["040101"]


def test_fetch_pagina_hasta_el_limite(db, monkeypatch):
    llamadas = _fake_client(
        [[{"a": str(i)} for i in range(2)], [{"a": "2"}]],
        monkeypatch,
    )
    salida = asyncio.run(core.fetch_mef_dataset("res-1", "t", limit=10, page_size=2))
    assert "3 registros" in salida
    assert len(llamadas) == 2
    assert llamadas[1].url.params["offset"] == "2"


def test_fetch_columnas_faltantes_en_el_primer_registro(db, monkeypatch):
    _fake_client([[{"a": "1"}, {"a": "2", "b": "x"}]], monkeypatch)
    asyncio.run(core.fetch_mef_dataset("res-1", "t", limit=10))
    schema = json.loads(core.mef_get_schema())
    assert schema["t"]["columnas"] == ["a", "b"]


def test_fetch_conserva_la_tabla_anterior_si_falla(db, monkeypatch):
    _fake_client([[{"a": "1"}]], monkeypatch)
    asyncio.run(core.fetch_mef_dataset("res-1", "t", limit=10))

    # Segunda descarga que revienta a mitad de la transacción: el ROLLBACK debe dejar la
    # tabla anterior intacta en vez de borrarla y no recrearla.
    _fake_client([[{"b": "nuevo"}]], monkeypatch)

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(core, "_register_download", _boom)
    salida = asyncio.run(core.fetch_mef_dataset("res-2", "t", limit=10))
    assert "Error" in salida or "Excepción" in salida
    assert json.loads(core.sql_mef_db("SELECT a FROM t"))["filas"] == [[1]]


def test_fetch_nombre_de_tabla_invalido(db):
    assert asyncio.run(core.fetch_mef_dataset("res", "tabla mala")).startswith("Error")


def test_fetch_sin_registros(db, monkeypatch):
    _fake_client([[]], monkeypatch)
    assert "No se encontraron registros" in asyncio.run(core.fetch_mef_dataset("res", "t"))


def test_fetch_error_http(db, monkeypatch):
    def handler(request):
        return httpx.Response(500, text="fallo del servidor")

    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **kw: _REAL_ASYNC_CLIENT(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )
    salida = asyncio.run(core.fetch_mef_dataset("res", "t"))
    assert salida.startswith("Error") and "500" in salida


@pytest.mark.parametrize("limite", [0, -5])
def test_fetch_limite_invalido(db, limite):
    assert asyncio.run(core.fetch_mef_dataset("res", "t", limit=limite)).startswith("Error")


# --- Descarga por streaming y tamaño del dataset --------------------------------

def test_fetch_avisa_de_lo_que_queda(db, monkeypatch):
    """Con datasets de millones de filas hay que saber cuánto falta tras un limit corto."""
    _fake_client([[{"a": "1"}, {"a": "2"}]], monkeypatch, total=1000)
    salida = asyncio.run(core.fetch_mef_dataset("res", "t", limit=2, page_size=2))
    assert "1000 filas en total" in salida
    assert "quedan 998" in salida
    assert "offset=2" in salida


def test_fetch_respeta_offset(db, monkeypatch):
    llamadas = _fake_client([[{"a": "1"}]], monkeypatch)
    asyncio.run(core.fetch_mef_dataset("res", "t", limit=1, offset=500))
    assert llamadas[0].url.params["offset"] == "500"


def test_fetch_offset_negativo(db):
    assert asyncio.run(core.fetch_mef_dataset("res", "t", offset=-1)).startswith("Error")


def test_fetch_recorta_page_size_al_maximo(db, monkeypatch):
    llamadas = _fake_client([[{"a": "1"}]], monkeypatch)
    asyncio.run(core.fetch_mef_dataset("res", "t", limit=10 ** 6, page_size=10 ** 6))
    assert int(llamadas[0].url.params["limit"]) == core.MAX_PAGE_SIZE


def test_fetch_columna_nueva_en_pagina_posterior(db, monkeypatch):
    """La API puede omitir un campo en una página y traerlo en la siguiente."""
    _fake_client([[{"a": "1"}], [{"a": "2", "b": "x"}]], monkeypatch)
    asyncio.run(core.fetch_mef_dataset("res", "t", limit=10, page_size=1))
    payload = json.loads(core.sql_mef_db("SELECT a, b FROM t ORDER BY a"))
    assert payload["filas"] == [[1, None], [2, "x"]]


def test_fetch_no_deja_tabla_de_staging(db, monkeypatch):
    _fake_client([[{"a": "1"}]], monkeypatch)
    asyncio.run(core.fetch_mef_dataset("res", "t", limit=1))
    with core._db() as conn:
        tablas = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert not any(t.startswith(core.STAGING_PREFIX) for t in tablas)


def test_fetch_progreso(db, monkeypatch):
    _fake_client([[{"a": "1"}], [{"a": "2"}]], monkeypatch, total=2)
    vistos = []
    asyncio.run(core.fetch_mef_dataset("res", "t", limit=2, page_size=1, progress=lambda d, t: vistos.append((d, t))))
    assert vistos == [(1, 2), (2, 2)]


def test_dataset_info(db, monkeypatch):
    _fake_client([[{"DEPARTAMENTO": "Arequipa", "MONTO": "1"}]], monkeypatch, total=7689615)
    info = json.loads(asyncio.run(core.mef_dataset_info("res")))
    assert info["filas_totales"] == 7689615
    assert info["columnas"] == 2
    assert info["nombres_de_columna"] == ["DEPARTAMENTO", "MONTO"]
    assert "páginas" in info["nota"] or "paginas" in info["nota"]


def test_dataset_info_resource_id_malo(db, monkeypatch):
    _fake_client([[]], monkeypatch)
    assert "resource_id" in asyncio.run(core.mef_dataset_info("no-existe"))

