from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_health_devuelve_el_contrato_exacto(settings_without_spa: Settings) -> None:
    with TestClient(create_app(settings_without_spa)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_responde_sin_hardware(settings_without_spa: Settings) -> None:
    """No hay radio Bluetooth ni dispositivo conectado y aun asi responde 200."""
    transport = httpx.ASGITransport(app=create_app(settings_without_spa))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_importar_la_app_no_abre_recursos() -> None:
    """Importar el modulo no debe conectar hardware ni base de datos."""
    import backend.app.main as main

    assert not hasattr(main.app.state, "light_device")
