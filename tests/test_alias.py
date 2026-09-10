"""El catálogo de alias debe servir para algo: resolverse allí donde se espera un resource_id."""
import asyncio
import json

import httpx

from mcp_mef import core

_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _mock_api(monkeypatch):
    """Devuelve la lista de resource_id que la API recibe, para comprobar la traducción."""
    pedidos = []

    def handler(request: httpx.Request) -> httpx.Response:
        pedidos.append(request.url.params.get("resource_id"))
        return httpx.Response(200, json={"records": [{"a": "1"}], "result": {"include_total": "1"}})

    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **kw: _REAL_ASYNC_CLIENT(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )
    return pedidos


def test_fetch_acepta_un_alias(db, monkeypatch):
    core.mef_register_dataset_alias("gasto_2026", "uuid-real-123", "Gasto mensual")
    pedidos = _mock_api(monkeypatch)
    asyncio.run(core.fetch_mef_dataset("gasto_2026", "gasto", limit=1))
    assert pedidos == ["uuid-real-123"]


def test_fetch_con_resource_id_directo(db, monkeypatch):
    pedidos = _mock_api(monkeypatch)
    asyncio.run(core.fetch_mef_dataset("uuid-suelto", "t", limit=1))
    assert pedidos == ["uuid-suelto"]


def test_dataset_info_acepta_un_alias(db, monkeypatch):
    core.mef_register_dataset_alias("ingresos", "uuid-ingresos")
    pedidos = _mock_api(monkeypatch)
    asyncio.run(core.mef_dataset_info("ingresos"))
    assert pedidos == ["uuid-ingresos"]


def test_alias_registrado_queda_en_la_metadata(db, monkeypatch):
    """Tras descargar por alias, la trazabilidad guarda el resource_id real, no el alias."""
    core.mef_register_dataset_alias("gasto_2026", "uuid-real-123")
    _mock_api(monkeypatch)
    asyncio.run(core.fetch_mef_dataset("gasto_2026", "gasto", limit=1))
    schema = json.loads(core.mef_get_schema())
    assert schema["gasto"]["resource_id"] == "uuid-real-123"


def test_remove_alias(db):
    core.mef_register_dataset_alias("temporal", "uuid-x")
    assert "borrado" in core.mef_remove_dataset_alias("temporal")
    assert json.loads(core.mef_list_known_datasets()) == []


def test_remove_alias_inexistente(db):
    core.mef_register_dataset_alias("otro", "uuid-y")
    assert "No había ningún alias" in core.mef_remove_dataset_alias("fantasma")


def test_remove_alias_sin_catalogo(db):
    assert "Aún no hay" in core.mef_remove_dataset_alias("cualquiera")


def test_remove_alias_vacio(db):
    assert core.mef_remove_dataset_alias("  ").startswith("Error")
