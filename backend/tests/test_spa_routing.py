from __future__ import annotations

from pathlib import Path

import pytest
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


@pytest.mark.parametrize(
    "path",
    [
        "/../pyproject.toml",
        "/../../etc/passwd",
        "/assets/../../pyproject.toml",
        "/%2e%2e/pyproject.toml",
        "/..%2Fpyproject.toml",
    ],
)
def test_ningun_recorrido_de_rutas_escapa_del_directorio_del_spa(
    settings_with_spa: Settings, tmp_path: Path, path: str
) -> None:
    """El catch-all resuelve archivos reales: sin la comprobacion de contencion
    serviria cualquier cosa del disco.

    El codigo ya lo hace bien (`candidate.is_relative_to(root)`), y justo por eso
    conviene fijarlo: la guarda es una linea facil de perder en un refactor y su
    ausencia no rompe ningun otro test.
    """
    secreto = tmp_path / "secreto.txt"
    secreto.write_text("no debe salir de aqui", encoding="utf-8")

    with TestClient(create_app(settings_with_spa)) as client:
        response = client.get(path)
        fuera = client.get(f"/../{secreto.name}")

    for served in (response, fuera):
        # O 404, o el index del SPA: nunca el contenido de un archivo de fuera.
        assert served.status_code in (200, 404)
        assert "no debe salir de aqui" not in served.text
        assert "led-room-backend" not in served.text
        if served.status_code == 200:
            assert "<!doctype html>" in served.text.lower()


def test_sin_frontend_arranca_en_modo_solo_api(settings_without_spa: Settings) -> None:
    with TestClient(create_app(settings_without_spa)) as client:
        health = client.get("/api/v1/health")
        root = client.get("/")

    assert health.status_code == 200
    assert root.status_code == 200
    assert root.json()["mode"] == "api-only"
