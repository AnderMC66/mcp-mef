"""Tests del buscador del portal y del listado de recursos, con la red simulada."""
import asyncio
import json

import httpx
import pytest

from mcp_mef import core

_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _fake_portal(monkeypatch, busquedas: dict, detalles: dict):
    """Simula las dos rutas del portal: búsqueda de datasets y detalle de uno.

    `busquedas` mapea término -> lista de datasets; `detalles`, slug -> lista de recursos.
    """
    peticiones = []

    def handler(request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content.decode())
        peticiones.append(cuerpo)
        if request.url.path.endswith("getDatasets"):
            datasets = busquedas.get(cuerpo["search"], [])
            return httpx.Response(200, json={
                "datasets": datasets or None,
                "countTotal": str(len(datasets)),
                "pagesCount": 1 if datasets else 0,
            })
        recursos = detalles.get(cuerpo["dataset"], [])
        return httpx.Response(200, json={"resources": recursos, "dataset_detail": {"dataset": cuerpo["dataset"]}})

    monkeypatch.setattr(
        core, "_portal_client",
        lambda: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), timeout=5),
    )
    return peticiones


_RECURSOS_GASTO = [
    {"resource_title": "2025-Gasto.csv", "resource_format": "CSV", "resource_id": "id-2025",
     "resource_url": "https://fs/2025.csv"},
    {"resource_title": "2026-Gasto-Mensual.csv", "resource_format": "csv", "resource_id": "id-2026",
     "resource_url": "https://fs/2026.csv"},
    {"resource_title": "Gastos_Diccionario.csv", "resource_format": "CSV", "resource_id": "id-dicc",
     "resource_url": "https://fs/dicc.csv"},
    {"resource_title": "manual.pdf", "resource_format": "PDF", "resource_id": "id-pdf",
     "resource_url": "https://fs/manual.pdf"},
]


def test_search_devuelve_slug_y_recursos(db, monkeypatch):
    _fake_portal(
        monkeypatch,
        {"gasto": [{"dataset_id": "presupuesto-y-ejecucion-de-gasto",
                    "dataset": "Presupuesto y Ejecución de Gasto", "formats": "CSV"}]},
        {"presupuesto-y-ejecucion-de-gasto": _RECURSOS_GASTO},
    )
    r = json.loads(asyncio.run(core.mef_search_datasets("gasto")))
    ds = r["datasets"][0]
    assert ds["slug"] == "presupuesto-y-ejecucion-de-gasto"
    assert ds["recursos"][0]["resource_id"] == "id-2025"
    # El PDF no es tabular: no debe aparecer entre los descargables.
    assert all(x["formato"].upper() != "PDF" for x in ds["recursos"])


def test_search_reintenta_con_una_palabra(db, monkeypatch):
    """El portal hace un LIKE con la frase entera, así que una frase larga no casa."""
    peticiones = _fake_portal(
        monkeypatch,
        {"presupuesto": [{"dataset_id": "s", "dataset": "Presupuesto", "formats": "CSV"}]},
        {"s": []},
    )
    r = json.loads(asyncio.run(core.mef_search_datasets("datos de presupuesto publico")))
    assert r["consulta"] == "presupuesto"
    assert "no dio resultados" in r["nota"]
    buscadas = [p["search"] for p in peticiones if "search" in p]
    assert buscadas == ["datos de presupuesto publico", "presupuesto"]


def test_search_sin_resultados(db, monkeypatch):
    _fake_portal(monkeypatch, {}, {})
    assert "No se encontraron datasets" in asyncio.run(core.mef_search_datasets("xyz"))


def test_search_sobrevive_a_un_detalle_caido(db, monkeypatch):
    """Si el detalle de un dataset falla, el resto de resultados debe seguir listándose."""
    def handler(request):
        if request.url.path.endswith("getDatasets"):
            return httpx.Response(200, json={
                "datasets": [{"dataset_id": "a", "dataset": "A", "formats": "CSV"}],
                "countTotal": "1", "pagesCount": 1,
            })
        return httpx.Response(500, text="boom")

    monkeypatch.setattr(
        core, "_portal_client",
        lambda: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), timeout=5),
    )
    r = json.loads(asyncio.run(core.mef_search_datasets("a")))
    assert r["datasets"][0]["slug"] == "a"
    assert "recursos" not in r["datasets"][0]


def test_list_resources(db, monkeypatch):
    _fake_portal(monkeypatch, {}, {"presupuesto-y-ejecucion-de-gasto": _RECURSOS_GASTO})
    r = json.loads(asyncio.run(core.mef_list_resources("presupuesto-y-ejecucion-de-gasto")))
    assert r["total_recursos"] == 4
    assert [x["resource_id"] for x in r["recursos"]][:2] == ["id-2025", "id-2026"]
    assert r["recursos"][0]["url_csv"] == "https://fs/2025.csv"


def test_list_resources_slug_inexistente(db, monkeypatch):
    _fake_portal(monkeypatch, {}, {})
    assert "no devolvió recursos" in asyncio.run(core.mef_list_resources("no-existe"))


@pytest.mark.parametrize("slug", ["", "   "])
def test_list_resources_slug_vacio(db, slug):
    assert asyncio.run(core.mef_list_resources(slug)).startswith("Error")
