"""`GET /api/v1/state`: la forma del estado global (README 31)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.doubles import api_settings

ADDRESS = "BE:FF:00:11:22:33"


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


def _state(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/v1/state")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_el_estado_inicial_tiene_la_forma_del_readme(client: TestClient) -> None:
    """Las claves de efecto y escena existen y valen null: se rellenan en Fases 5 y 6."""
    assert _state(client) == {
        "version": 0,
        "device": None,
        "light": {"power": False, "color": "#FFFFFF", "brightness": 100},
        "effect": None,
        "scene": None,
    }


def test_la_version_crece_con_cada_cambio_aceptado(client: TestClient) -> None:
    device = client.post("/api/v1/devices", json={"name": "Tira", "address": ADDRESS}).json()
    client.post(f"/api/v1/devices/{device['id']}/connect")

    before = _state(client)["version"]
    client.post("/api/v1/lights/power", json={"on": True})
    after = _state(client)["version"]

    assert after > before


def test_el_estado_describe_el_enlace_tras_conectar(client: TestClient) -> None:
    device = client.post("/api/v1/devices", json={"name": "Tira", "address": ADDRESS}).json()
    client.post(f"/api/v1/devices/{device['id']}/connect")

    state = _state(client)

    assert state["device"] == {
        "device_id": device["id"],
        "connected": True,
        "rssi": None,
        "last_error": None,
    }


def test_el_estado_no_se_lee_del_dispositivo_sino_del_store(client: TestClient) -> None:
    """El adaptador es un sumidero: desconectar no borra el ultimo estado deseado."""
    device = client.post("/api/v1/devices", json={"name": "Tira", "address": ADDRESS}).json()
    client.post(f"/api/v1/devices/{device['id']}/connect")
    client.put("/api/v1/lights/color", json={"r": 123, "g": 0, "b": 255})

    client.post(f"/api/v1/devices/{device['id']}/disconnect")
    state = _state(client)

    assert state["device"]["connected"] is False
    assert state["light"]["color"] == "#7B00FF"
