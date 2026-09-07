"""Rutas de perfiles: CRUD y activacion delegada en escenas.

La activacion de un perfil se prueba de extremo a extremo porque lo interesante
no es que responda 200, sino **que escena** deja activa y que llega al estado
global exactamente igual que si se hubiera activado esa escena a mano.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.doubles import api_settings

ADDRESS = "BE:FF:00:11:22:33"

ESTATICO: dict[str, Any] = {
    "name": "Morado fijo",
    "type": "STATIC",
    "steps": [{"color": "#7B00FF"}],
}


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
def device(client: TestClient) -> dict[str, Any]:
    created = client.post("/api/v1/devices", json={"name": "Tira", "address": ADDRESS})
    registered: dict[str, Any] = created.json()
    assert client.post(f"/api/v1/devices/{registered['id']}/connect").status_code == 200
    return registered


def _crear_escena(client: TestClient, device_id: str, nombre: str) -> str:
    efecto = client.post("/api/v1/effects", json={**ESTATICO, "name": f"{nombre} fx"})
    assert efecto.status_code == 201, efecto.text
    response = client.post(
        "/api/v1/scenes",
        json={
            "name": nombre,
            "targets": [{"device_id": device_id, "effect_id": efecto.json()["id"]}],
        },
    )
    assert response.status_code == 201, response.text
    identifier: str = response.json()["id"]
    return identifier


def _crear_perfil(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/v1/profiles", json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def test_el_catalogo_de_perfiles_arranca_vacio(client: TestClient) -> None:
    response = client.get("/api/v1/profiles")

    assert response.status_code == 200
    assert response.json() == []


def test_crear_un_perfil_numera_sus_escenas_por_el_orden_del_array(
    client: TestClient, device: dict[str, Any]
) -> None:
    """La posicion es el indice: dos escenas en la misma posicion son irrepresentables."""
    primera = _crear_escena(client, device["id"], "Cyberpunk")
    segunda = _crear_escena(client, device["id"], "Purple pulse")

    creado = _crear_perfil(
        client,
        {
            "name": "Gaming",
            "icon": "gamepad",
            "scenes": [{"scene_id": primera}, {"scene_id": segunda, "is_default": True}],
        },
    )

    assert [scene["position"] for scene in creado["scenes"]] == [0, 1]
    assert creado["default_scene_id"] == segunda


def test_el_perfil_publica_la_escena_que_activaria(
    client: TestClient, device: dict[str, Any]
) -> None:
    """Se resuelve en el servidor para que la UI no reimplemente el desempate."""
    primera = _crear_escena(client, device["id"], "Cyberpunk")
    segunda = _crear_escena(client, device["id"], "Purple pulse")

    creado = _crear_perfil(
        client,
        {"name": "Gaming", "scenes": [{"scene_id": primera}, {"scene_id": segunda}]},
    )

    assert creado["default_scene_id"] == primera


def test_un_perfil_sin_escenas_no_tiene_escena_predeterminada(client: TestClient) -> None:
    creado = _crear_perfil(client, {"name": "Vacio"})

    assert creado["scenes"] == []
    assert creado["default_scene_id"] is None


def test_un_perfil_creado_se_lee_y_se_lista(client: TestClient, device: dict[str, Any]) -> None:
    escena = _crear_escena(client, device["id"], "Noche")
    creado = _crear_perfil(client, {"name": "Sleep", "scenes": [{"scene_id": escena}]})

    leido = client.get(f"/api/v1/profiles/{creado['id']}")
    listado = client.get("/api/v1/profiles")

    assert leido.json() == creado
    assert listado.json() == [creado]


def test_reemplazar_un_perfil_conserva_su_identificador(
    client: TestClient, device: dict[str, Any]
) -> None:
    escena = _crear_escena(client, device["id"], "Noche")
    creado = _crear_perfil(client, {"name": "Sleep", "scenes": [{"scene_id": escena}]})

    response = client.put(
        f"/api/v1/profiles/{creado['id']}",
        json={"name": "Sleep v2", "scenes": []},
    )

    assert response.status_code == 200
    assert response.json()["id"] == creado["id"]
    assert response.json()["scenes"] == []


def test_reemplazar_un_perfil_inexistente_no_lo_crea(client: TestClient) -> None:
    response = client.put(f"/api/v1/profiles/{uuid4()}", json={"name": "Fantasma"})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "profile_not_found"
    assert client.get("/api/v1/profiles").json() == []


def test_un_perfil_hacia_una_escena_inexistente_es_un_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/profiles",
        json={"name": "Roto", "scenes": [{"scene_id": str(uuid4())}]},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_payload"


def test_borrar_un_perfil_responde_204_y_conserva_sus_escenas(
    client: TestClient, device: dict[str, Any]
) -> None:
    escena = _crear_escena(client, device["id"], "Noche")
    creado = _crear_perfil(client, {"name": "Sleep", "scenes": [{"scene_id": escena}]})

    assert client.delete(f"/api/v1/profiles/{creado['id']}").status_code == 204
    assert client.get("/api/v1/profiles").json() == []
    assert client.get(f"/api/v1/scenes/{escena}").status_code == 200


def test_borrar_un_perfil_inexistente_es_un_404(client: TestClient) -> None:
    response = client.delete(f"/api/v1/profiles/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "profile_not_found"


def test_activar_un_perfil_deja_puesta_su_escena_predeterminada(
    client: TestClient, device: dict[str, Any]
) -> None:
    primera = _crear_escena(client, device["id"], "Cyberpunk")
    segunda = _crear_escena(client, device["id"], "Purple pulse")
    creado = _crear_perfil(
        client,
        {
            "name": "Gaming",
            "scenes": [{"scene_id": primera}, {"scene_id": segunda, "is_default": True}],
        },
    )

    response = client.post(f"/api/v1/profiles/{creado['id']}/activate")

    assert response.status_code == 200
    assert response.json() == {"profile_id": creado["id"], "scene": {"id": segunda}}
    assert client.get("/api/v1/state").json()["scene"] == {"id": segunda}


def test_activar_un_perfil_sin_escenas_responde_409(client: TestClient) -> None:
    creado = _crear_perfil(client, {"name": "Vacio"})

    response = client.post(f"/api/v1/profiles/{creado['id']}/activate")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "nothing_to_activate"


def test_activar_un_perfil_inexistente_es_un_404(client: TestClient) -> None:
    response = client.post(f"/api/v1/profiles/{uuid4()}/activate")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "profile_not_found"


def test_activar_un_perfil_sin_enlace_falla_igual_que_activar_su_escena(
    client: TestClient,
) -> None:
    """Los errores de activar un perfil son los de activar una escena: es la misma operacion."""
    registrado = client.post("/api/v1/devices", json={"name": "Tira", "address": ADDRESS}).json()
    escena = _crear_escena(client, registrado["id"], "Noche")
    creado = _crear_perfil(client, {"name": "Sleep", "scenes": [{"scene_id": escena}]})

    response = client.post(f"/api/v1/profiles/{creado['id']}/activate")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "device_not_connected"


def test_las_rutas_de_perfiles_estan_en_el_openapi(client: TestClient) -> None:
    rutas = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/profiles" in rutas
    assert "/api/v1/profiles/{profile_id}" in rutas
    assert "/api/v1/profiles/{profile_id}/activate" in rutas
