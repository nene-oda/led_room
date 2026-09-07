"""Arranque y, sobre todo, APAGADO: lo que debe liberarse pase lo que pase.

El apagado nunca se prueba solo, y es donde estaban los dos fallos: el engine se
cerraba en un `finally` **detras** de `disconnect()`, asi que un adaptador que
lanzara al soltar el enlace dejaba SQLite sin cerrar; y `disconnect()` no tenia
timeout, asi que un `BleakClient` colgado bloqueaba el `lifespan` para siempre
hasta que Docker mataba el contenedor (con el WAL sin checkpoint).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from backend.app import main
from backend.app.api.deps import resources_of
from backend.app.config import Settings
from backend.app.domain.devices.ports import LightDevicePort
from backend.app.infrastructure.persistence.database import create_database_engine
from backend.app.main import create_app
from backend.tests.doubles import RecordingLightDevice, api_settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return api_settings(tmp_path)


class ExplodingOnDisconnect(RecordingLightDevice):
    """El adaptador falla justo al soltar el enlace."""

    async def disconnect(self) -> None:
        raise RuntimeError("el enlace exploto al cerrarse")


class HangingOnDisconnect(RecordingLightDevice):
    """`disconnect()` no retorna nunca: es el `BleakClient` colgado de la Fase 1."""

    async def disconnect(self) -> None:
        await asyncio.Event().wait()


def _spy_engine(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> list[str]:
    """Deja el engine real en su sitio y anota cuando se le llama a `dispose`."""
    engine: Engine = create_database_engine(settings.database)
    disposals: list[str] = []
    original = engine.dispose

    def dispose(*args: object, **kwargs: object) -> None:
        disposals.append("dispose")
        original()

    monkeypatch.setattr(engine, "dispose", dispose)
    monkeypatch.setattr(main, "create_database_engine", lambda *a, **k: engine)
    return disposals


def _use_device(monkeypatch: pytest.MonkeyPatch, device: LightDevicePort) -> None:
    monkeypatch.setattr(main, "build_light_device", lambda _: device)


def test_el_engine_se_cierra_aunque_soltar_el_enlace_falle(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    disposals = _spy_engine(monkeypatch, settings)
    _use_device(monkeypatch, ExplodingOnDisconnect())

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").status_code == 200

    assert disposals == ["dispose"], "Un fallo al desconectar dejaba SQLite sin cerrar"


def test_un_disconnect_colgado_no_bloquea_el_apagado(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se acota con `LED_ROOM_BLE_WRITE_TIMEOUT`, la misma cota que ya rige el enlace."""
    acotado = settings.model_copy(update={"ble_write_timeout": 0.2})
    disposals = _spy_engine(monkeypatch, acotado)
    _use_device(monkeypatch, HangingOnDisconnect())

    inicio = time.perf_counter()
    with TestClient(create_app(acotado)) as client:
        assert client.get("/api/v1/health").status_code == 200
    transcurrido = time.perf_counter() - inicio

    assert transcurrido < 5.0, f"El apagado tardo {transcurrido:.1f} s: quedo colgado"
    assert disposals == ["dispose"]


def test_los_limitadores_no_dejan_tareas_vivas_tras_el_apagado(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cancel_all` esta registrado en el `AsyncExitStack`, no en un `finally` fragil."""
    _use_device(monkeypatch, ExplodingOnDisconnect())

    app = create_app(settings)
    with TestClient(app) as client:
        client.post("/api/v1/devices", json={"name": "Tira", "address": "BE:FF:00:11:22:33"})
        throttles = resources_of(app).throttles

    assert throttles.color._task is None
    assert throttles.brightness._task is None
