"""La persistencia sincrona no puede ejecutarse EN el bucle de eventos.

Tres docstrings del proyecto afirmaban que "FastAPI ejecuta las dependencias
sincronas en el threadpool, asi que SQLite no detiene el bucle". Solo era cierto
para abrir y cerrar la `Session`: las consultas las hace la ruta, que es `async`,
y por tanto corrian en el bucle. Con `PRAGMA busy_timeout=5000`, un escritor
concurrente lo congelaba hasta 5 s: sin escrituras BLE, sin difusion y sin
`/health`.

Este test es el guardian de la correccion. Sin el, quitar un `run_in_threadpool`
no rompe absolutamente nada visible.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import deps
from backend.app.config import Settings
from backend.app.domain.devices.models import Device
from backend.app.domain.devices.repositories import DeviceRepository
from backend.app.domain.lighting import LightState
from backend.app.main import create_app
from backend.tests.doubles import InMemoryDeviceRepository, api_settings

ADDRESS = "BE:FF:00:11:22:33"


def _in_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class LoopAwareRepository(InMemoryDeviceRepository):
    """Anota, por metodo, si se le llamo desde dentro del bucle de eventos."""

    calls: ClassVar[dict[str, list[bool]]] = {}

    def _note(self, name: str) -> None:
        LoopAwareRepository.calls.setdefault(name, []).append(_in_event_loop())

    def list_enabled(self) -> Sequence[Device]:
        self._note("list_enabled")
        return super().list_enabled()

    def upsert(self, device: Device) -> Device:
        self._note("upsert")
        return super().upsert(device)

    def get(self, device_id: UUID) -> Device | None:
        self._note("get")
        return super().get(device_id)

    def save_state(self, device_id: UUID, state: LightState) -> None:
        self._note("save_state")
        super().save_state(device_id, state)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return api_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    LoopAwareRepository.calls = {}
    shared = LoopAwareRepository()

    def factory() -> DeviceRepository:
        return shared

    app: FastAPI = create_app(settings)
    app.dependency_overrides[deps.get_device_repository] = factory
    with TestClient(app) as client:
        yield client


def test_las_rutas_no_consultan_la_base_desde_el_bucle_de_eventos(client: TestClient) -> None:
    created: dict[str, Any] = client.post(
        "/api/v1/devices", json={"name": "Tira", "address": ADDRESS}
    ).json()
    device_id = created["id"]

    assert client.post(f"/api/v1/devices/{device_id}/connect").status_code == 200
    assert client.post("/api/v1/lights/power", json={"on": True}).status_code == 200
    assert client.get("/api/v1/devices").status_code == 200
    assert client.get(f"/api/v1/devices/{device_id}").status_code == 200

    # `get` queda fuera a proposito: lo llama `DeviceService.connect`, que es una
    # corrutina, desde DENTRO del bucle. Sacarlo de ahi exigiria que la capa de
    # aplicacion importara Starlette, y eso invierte la direccion de las
    # dependencias (lo vigila `test_application_boundaries.py`). Es una lectura
    # de una fila por clave primaria, no un `commit()`, asi que se acepta: lo que
    # no puede correr en el bucle es lo que espera a otro escritor.
    frontera = {"list_enabled", "upsert", "save_state"}
    for name in sorted(frontera):
        llamadas = LoopAwareRepository.calls.get(name, [])
        assert llamadas, f"{name} no llego a llamarse: el test no probaria nada"
        assert not any(llamadas), (
            f"{name} corrio en el bucle de eventos: envuelvelo en `run_in_threadpool`"
        )


def test_el_commit_del_estado_deseado_nunca_bloquea_el_bucle(client: TestClient) -> None:
    """`save_state` hace `commit()`: es la llamada que puede esperar `busy_timeout`."""
    created: dict[str, Any] = client.post(
        "/api/v1/devices", json={"name": "Tira", "address": ADDRESS}
    ).json()
    client.post(f"/api/v1/devices/{created['id']}/connect")
    LoopAwareRepository.calls.pop("save_state", None)

    client.put("/api/v1/lights/color", json={"r": 1, "g": 2, "b": 3})
    client.put("/api/v1/lights/brightness", json={"brightness": 40})

    assert LoopAwareRepository.calls["save_state"] == [False, False]
