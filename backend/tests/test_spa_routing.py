from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_raiz_sirve_el_spa(settings_with_spa: Settings) -> None:
    with TestClient(create_app(settings_with_spa)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "<!doctype html>" in response.text.lower()


def test_ruta_profunda_del_cliente_devuelve_el_spa(settings_with_spa: Settings) -> None:
    """Recargar una URL interna no debe dar 404."""
    with TestClient(create_app(settings_with_spa)) as client:
        response = client.get("/scenes/night")

    assert response.status_code == 200
    assert "<!doctype html>" in response.text.lower()


def test_ruta_de_api_inexistente_devuelve_404_json(settings_with_spa: Settings) -> None:
    """El catch-all no debe ensombrecer /api/v1."""
    with TestClient(create_app(settings_with_spa)) as client:
        response = client.get("/api/v1/nope")

    assert response.status_code == 404
    assert "<!doctype html>" not in response.text.lower()


def test_ws_no_devuelve_el_spa(settings_with_spa: Settings) -> None:
    """La ruta /ws queda reservada para la fase de tiempo real."""
    with TestClient(create_app(settings_with_spa)) as client:
        response = client.get("/ws")

    assert response.status_code == 404
    assert "<!doctype html>" not in response.text.lower()


def test_archivo_estatico_real_se_sirve_tal_cual(settings_with_spa: Settings) -> None:
    with TestClient(create_app(settings_with_spa)) as client:
        response = client.get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert "led-room" in response.text


def test_archivo_de_raiz_no_cae_en_el_fallback(settings_with_spa: Settings) -> None:
    """Un manifest real debe servirse, no el HTML del indice (PWA, Fase 8)."""
    with TestClient(create_app(settings_with_spa)) as client:
        response = client.get("/manifest.webmanifest")

    assert response.status_code == 200
    assert "<!doctype html>" not in response.text.lower()


def test_sin_frontend_arranca_en_modo_solo_api(settings_without_spa: Settings) -> None:
    with TestClient(create_app(settings_without_spa)) as client:
        health = client.get("/api/v1/health")
        root = client.get("/")

    assert health.status_code == 200
    assert root.status_code == 200
    assert root.json()["mode"] == "api-only"
