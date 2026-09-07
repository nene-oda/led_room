"""Rutas de control de la luz: camino feliz, rangos, capacidades y persistencia.

El adaptador nulo cumple `LightDevicePort` y basta para el camino feliz. Los
casos raros (sin capacidad de brillo, escritura fallida, base que no acepta la
escritura) se inyectan por `dependency_overrides`, no simulando hardware.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from backend.app.api import deps
from backend.app.application.light_service import LightService
from backend.app.config import Settings
from backend.app.domain.devices.models import SINGLE_COLOR_STRIP
from backend.app.domain.devices.ports import DeviceError
from backend.app.domain.devices.repositories import DeviceRepository
from backend.app.domain.lighting import LightState
from backend.app.infrastructure.persistence.database import create_database_engine
from backend.app.infrastructure.persistence.models.device import DeviceStateRecord
from backend.app.main import create_app
from backend.tests.doubles import (
    ConnectedLightDevice,
    InMemoryDeviceRepository,
    api_settings,
)

ADDRESS = "BE:FF:00:11:22:33"
PURPLE = {"r": 123, "g": 0, "b": 255}


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


@pytest.fixture
def connected(client: TestClient) -> dict[str, Any]:
    """Un dispositivo registrado y con el enlace abierto."""
    created = client.post("/api/v1/devices", json={"name": "Tira", "address": ADDRESS})
    device: dict[str, Any] = created.json()
    assert client.post(f"/api/v1/devices/{device['id']}/connect").status_code == 200
    return device


def _override_light_service(app: FastAPI, device: ConnectedLightDevice) -> None:
    """Sustituye el dispositivo que recibe las escrituras, no el estado del enlace.

    Estos tests piden ademas el fixture `connected`: la fuente de verdad de
    "hay un dispositivo conectado" es el store (ver `LightService`), asi que sin
    abrir el enlace la respuesta seria 409 `device_not_connected` y el test no
    llegaria a probar lo suyo.
    """

    def factory(resources: deps.ResourcesDep) -> LightService:
        return LightService(device, resources.store)

    app.dependency_overrides[deps.get_light_service] = factory


def _stored_state(settings: Settings, device_id: str) -> DeviceStateRecord | None:
    """Lee la fila `device_state` con un engine aparte, como lo haria un reinicio."""
    engine = create_database_engine(settings.database)
    try:
        with Session(engine) as session:
            return session.get(DeviceStateRecord, UUID(device_id))
    finally:
        engine.dispose()


def test_sin_dispositivo_conectado_encender_devuelve_409(client: TestClient) -> None:
    response = client.post("/api/v1/lights/power", json={"on": True})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "device_not_connected"


def test_encender_devuelve_el_estado_deseado(client: TestClient, connected: dict[str, Any]) -> None:
    response = client.post("/api/v1/lights/power", json={"on": True})

    assert response.status_code == 200
    assert response.json() == {"power": True, "color": "#FFFFFF", "brightness": 100}


def test_el_color_se_devuelve_en_hexadecimal_mayusculas(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """Mutacion en {r,g,b}, lectura en #RRGGBB: son las dos formas canonicas."""
    response = client.put("/api/v1/lights/color", json=PURPLE)

    assert response.status_code == 200
    assert response.json()["color"] == "#7B00FF"


def test_el_brillo_se_aplica_y_se_devuelve(client: TestClient, connected: dict[str, Any]) -> None:
    response = client.put("/api/v1/lights/brightness", json={"brightness": 60})

    assert response.status_code == 200
    assert response.json()["brightness"] == 60


def test_un_canal_fuera_de_rango_devuelve_422(
    client: TestClient, connected: dict[str, Any]
) -> None:
    response = client.put("/api/v1/lights/color", json={"r": 300, "g": 0, "b": 0})

    assert response.status_code == 422
    body = response.json()["detail"]
    assert body["code"] == "invalid_payload"
    assert "r" in body["message"]


def test_un_brillo_mayor_que_cien_devuelve_422(
    client: TestClient, connected: dict[str, Any]
) -> None:
    response = client.put("/api/v1/lights/brightness", json={"brightness": 101})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_payload"


def test_cada_intencion_del_usuario_persiste_el_estado_deseado(
    client: TestClient, connected: dict[str, Any], settings: Settings
) -> None:
    """Una peticion HTTP es una intencion deliberada: ahi si se escribe en la base."""
    client.post("/api/v1/lights/power", json={"on": True})
    client.put("/api/v1/lights/color", json=PURPLE)
    client.put("/api/v1/lights/brightness", json={"brightness": 40})

    stored = _stored_state(settings, connected["id"])

    assert stored is not None
    assert stored.power is True
    # MAYUSCULAS: el CHECK ... GLOB de la tabla rechaza cualquier otra cosa.
    assert stored.color_hex == "#7B00FF"
    assert stored.brightness == 40


def test_el_estado_persistido_se_reaplica_al_reconectar(
    client: TestClient, connected: dict[str, Any]
) -> None:
    client.put("/api/v1/lights/color", json=PURPLE)
    client.post(f"/api/v1/devices/{connected['id']}/disconnect")

    client.post(f"/api/v1/devices/{connected['id']}/connect")

    assert client.get("/api/v1/state").json()["light"]["color"] == "#7B00FF"


def test_sin_capacidad_de_brillo_la_peticion_se_rechaza_con_409(
    app: FastAPI, client: TestClient, connected: dict[str, Any]
) -> None:
    device = ConnectedLightDevice(
        capabilities=SINGLE_COLOR_STRIP.model_copy(update={"brightness": False})
    )
    _override_light_service(app, device)

    response = client.put("/api/v1/lights/brightness", json={"brightness": 60})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "unsupported_capability"
    # La guardia se comprueba ANTES de tocar el dispositivo.
    assert device.operations == []


def test_un_fallo_de_escritura_del_dispositivo_devuelve_502(
    app: FastAPI, client: TestClient, connected: dict[str, Any]
) -> None:
    device = ConnectedLightDevice()
    device.failure = DeviceError("el enlace se cayo a mitad de la trama")
    _override_light_service(app, device)

    response = client.post("/api/v1/lights/power", json={"on": True})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "device_write_failed"


def test_un_fallo_al_persistir_no_convierte_en_error_un_comando_aplicado(
    app: FastAPI, client: TestClient, connected: dict[str, Any]
) -> None:
    """SQLite es la cache de arranque, no la fuente de verdad (NEXT_STEPS A4)."""

    class BrokenRepository(InMemoryDeviceRepository):
        def save_state(self, device_id: UUID, state: LightState) -> None:
            raise RuntimeError("disco lleno")

    def factory() -> DeviceRepository:
        return BrokenRepository()

    app.dependency_overrides[deps.get_device_repository] = factory

    response = client.post("/api/v1/lights/power", json={"on": True})

    assert response.status_code == 200
    assert response.json()["power"] is True
