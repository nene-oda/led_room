"""Politica de errores en la frontera: cuerpo uniforme y sin trazas (NEXT_STEPS A6).

Lo que se prueba aqui no es que cada ruta devuelva su codigo (eso esta en los
tests de cada ruta), sino que **la forma** del error sea siempre la misma y que
un 500 no filtre nada del interior.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import deps
from backend.app.application.state_store import StateStore
from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.doubles import api_settings

SECRET = "SELECT token FROM sesiones"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return api_settings(tmp_path)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def test_un_error_de_dominio_tiene_exactamente_las_claves_del_contrato(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/lights/power", json={"on": True})

    assert response.status_code == 409
    assert set(response.json()) == {"detail"}
    assert set(response.json()["detail"]) == {"code", "message"}


def test_un_422_de_esquema_usa_el_mismo_cuerpo_que_uno_de_dominio(client: TestClient) -> None:
    """Sin este handler, el mismo rango invalido tendria dos formas distintas."""
    response = client.put("/api/v1/lights/brightness", json={"brightness": "mucho"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_payload"
    assert "brightness" in detail["message"]


def test_un_cuerpo_ausente_se_rechaza_con_el_cuerpo_uniforme(client: TestClient) -> None:
    response = client.post("/api/v1/lights/power")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_payload"


def test_un_fallo_interno_no_filtra_nada_del_servidor(app: FastAPI, settings: Settings) -> None:
    def broken() -> StateStore:
        raise RuntimeError(SECRET)

    app.dependency_overrides[deps.get_store] = broken

    # `ServerErrorMiddleware` responde y despues re-lanza para que el servidor lo
    # registre; en un test hay que pedir explicitamente que no se propague.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/state")

    assert response.status_code == 500
    assert response.json() == {
        "detail": {"code": "internal_error", "message": "Error interno del servidor."}
    }
    assert SECRET not in response.text
    assert "Traceback" not in response.text


def test_una_ruta_de_api_inexistente_sigue_devolviendo_404_json(client: TestClient) -> None:
    """El catch-all del SPA no puede ensombrecer /api/v1 (contrato congelado)."""
    response = client.get("/api/v1/typo")

    assert response.status_code == 404
    assert "<!doctype html>" not in response.text.lower()
    assert "detail" in response.json()


def test_rest_y_websocket_traducen_el_mismo_fallo_al_mismo_codigo(client: TestClient) -> None:
    """La politica vive en `translate_error`: los dos transportes la comparten."""
    rest = client.post("/api/v1/lights/power", json={"on": True})

    with client.websocket_connect("/ws") as websocket:
        assert websocket.receive_json()["type"] == "state.snapshot"
        websocket.send_json({"type": "light.power", "payload": {"on": True}})
        frame = websocket.receive_json()

    assert rest.json()["detail"]["code"] == frame["payload"]["code"] == "device_not_connected"
