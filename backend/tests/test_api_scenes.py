"""Rutas de escenas: CRUD, activacion y la politica de errores compartida.

Se prueba la aplicacion entera, con el adaptador nulo y una base temporal: es la
unica forma de comprobar que un 409 del dominio sale con el cuerpo uniforme, que
`scene.activated` llega por el WebSocket y que activar una escena no escribe ni
una fila.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from backend.app.config import Settings
from backend.app.infrastructure.persistence.database import create_database_engine
from backend.app.infrastructure.persistence.models.device import DeviceStateRecord
from backend.app.main import create_app
from backend.tests.doubles import api_settings

ADDRESS = "BE:FF:00:11:22:33"

ESTATICO: dict[str, Any] = {
    "name": "Morado fijo",
    "type": "STATIC",
    "steps": [{"color": "#7B00FF"}],
}

CICLO: dict[str, Any] = {
    "name": "Cyberpunk",
    "type": "SMOOTH_CYCLE",
    "loop": True,
    "transition_ms": 3000,
    "steps": [{"color": "#009DFF"}, {"color": "#FF008C"}],
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
    """Un dispositivo registrado y con el enlace abierto."""
    created = client.post("/api/v1/devices", json={"name": "Tira", "address": ADDRESS})
    registered: dict[str, Any] = created.json()
    assert client.post(f"/api/v1/devices/{registered['id']}/connect").status_code == 200
    return registered


def _crear_efecto(client: TestClient, body: dict[str, Any]) -> str:
    response = client.post("/api/v1/effects", json=body)
    assert response.status_code == 201, response.text
    identifier: str = response.json()["id"]
    return identifier


def _crear_escena(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/v1/scenes", json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def _escena(device_id: str, effect_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": "Noche",
        "icon": "moon",
        "targets": [{"device_id": device_id, "effect_id": effect_id, **extra}],
    }


def test_el_catalogo_de_escenas_arranca_vacio(client: TestClient) -> None:
    """Una base recien migrada no se siembra con escenas (ARCHITECTURE 7.5)."""
    response = client.get("/api/v1/scenes")

    assert response.status_code == 200
    assert response.json() == []


def test_crear_una_escena_devuelve_201_con_su_identidad(
    client: TestClient, device: dict[str, Any]
) -> None:
    efecto = _crear_efecto(client, ESTATICO)

    creada = _crear_escena(client, _escena(device["id"], efecto, brightness=10))

    assert creada["name"] == "Noche"
    assert creada["icon"] == "moon"
    assert creada["is_builtin"] is False
    assert creada["targets"] == [
        {
            "device_id": device["id"],
            "effect_id": efecto,
            "brightness": 10,
            "speed": None,
            "enabled": True,
        }
    ]


def test_una_escena_creada_se_lee_y_se_lista(client: TestClient, device: dict[str, Any]) -> None:
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, ESTATICO)))

    leida = client.get(f"/api/v1/scenes/{creada['id']}")
    listado = client.get("/api/v1/scenes")

    assert leida.json() == creada
    assert listado.json() == [creada]


def test_reemplazar_una_escena_conserva_su_identificador(
    client: TestClient, device: dict[str, Any]
) -> None:
    efecto = _crear_efecto(client, ESTATICO)
    creada = _crear_escena(client, _escena(device["id"], efecto))

    response = client.put(
        f"/api/v1/scenes/{creada['id']}",
        json={**_escena(device["id"], efecto), "name": "Noche v2", "targets": []},
    )

    assert response.status_code == 200
    assert response.json()["id"] == creada["id"]
    assert response.json()["name"] == "Noche v2"
    assert response.json()["targets"] == []


def test_reemplazar_una_escena_inexistente_no_la_crea(
    client: TestClient, device: dict[str, Any]
) -> None:
    inventado = str(uuid4())

    response = client.put(
        f"/api/v1/scenes/{inventado}",
        json=_escena(device["id"], _crear_efecto(client, ESTATICO)),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "scene_not_found"
    assert client.get("/api/v1/scenes").json() == []


def test_duplicar_una_escena_crea_otra_con_los_mismos_objetivos(
    client: TestClient, device: dict[str, Any]
) -> None:
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, ESTATICO)))

    response = client.post(f"/api/v1/scenes/{creada['id']}/duplicate")

    assert response.status_code == 201
    copia = response.json()
    assert copia["id"] != creada["id"]
    assert copia["name"] == "Noche (copia)"
    assert copia["targets"] == creada["targets"]
    assert len(client.get("/api/v1/scenes").json()) == 2


def test_duplicar_una_escena_admite_un_nombre_propio(
    client: TestClient, device: dict[str, Any]
) -> None:
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, ESTATICO)))

    response = client.post(f"/api/v1/scenes/{creada['id']}/duplicate", json={"name": "Noche B"})

    assert response.json()["name"] == "Noche B"


def test_borrar_una_escena_responde_204_y_deja_de_listarla(
    client: TestClient, device: dict[str, Any]
) -> None:
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, ESTATICO)))

    assert client.delete(f"/api/v1/scenes/{creada['id']}").status_code == 204
    assert client.get("/api/v1/scenes").json() == []


def test_borrar_una_escena_inexistente_es_un_404(client: TestClient) -> None:
    response = client.delete(f"/api/v1/scenes/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "scene_not_found"


def test_un_objetivo_hacia_un_efecto_inexistente_es_un_422(
    client: TestClient, device: dict[str, Any]
) -> None:
    response = client.post("/api/v1/scenes", json=_escena(device["id"], str(uuid4())))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_payload"


def test_dos_objetivos_para_el_mismo_dispositivo_son_un_422(
    client: TestClient, device: dict[str, Any]
) -> None:
    efecto = _crear_efecto(client, ESTATICO)
    body = _escena(device["id"], efecto)
    body["targets"].append({"device_id": device["id"], "effect_id": efecto})

    response = client.post("/api/v1/scenes", json=body)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_payload"


def test_activar_una_escena_devuelve_su_identificador(
    client: TestClient, device: dict[str, Any]
) -> None:
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, ESTATICO)))

    response = client.post(f"/api/v1/scenes/{creada['id']}/activate")

    assert response.status_code == 200
    assert response.json() == {"id": creada["id"]}


def test_la_escena_activa_aparece_en_el_estado_global(
    client: TestClient, device: dict[str, Any]
) -> None:
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, CICLO)))

    client.post(f"/api/v1/scenes/{creada['id']}/activate")

    estado = client.get("/api/v1/state").json()
    assert estado["scene"] == {"id": creada["id"]}
    assert estado["effect"]["running"] is True


def test_un_comando_manual_deja_el_estado_global_sin_escena(
    client: TestClient, device: dict[str, Any]
) -> None:
    """`scene` con `effect: null` describiria una escena que ya no suena."""
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, CICLO)))
    client.post(f"/api/v1/scenes/{creada['id']}/activate")

    assert client.put("/api/v1/lights/color", json={"r": 0, "g": 157, "b": 255}).status_code == 200

    estado = client.get("/api/v1/state").json()
    assert estado["scene"] is None
    assert estado["effect"] is None


def test_arrancar_un_efecto_suelto_deja_el_estado_global_sin_escena(
    client: TestClient, device: dict[str, Any]
) -> None:
    """Un efecto que no pertenece a la escena tambien le quita el control."""
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, CICLO)))
    suelto = _crear_efecto(client, {**CICLO, "name": "Suelto"})
    client.post(f"/api/v1/scenes/{creada['id']}/activate")

    assert client.post(f"/api/v1/effects/{suelto}/start").status_code == 200

    estado = client.get("/api/v1/state").json()
    assert estado["scene"] is None
    assert estado["effect"]["id"] == suelto


def test_soltar_la_escena_llega_a_los_clientes_del_websocket(
    client: TestClient, device: dict[str, Any]
) -> None:
    """Ningun evento congelado dice "la escena ya no esta activa" (ARCHITECTURE 3.6)."""
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, CICLO)))
    client.post(f"/api/v1/scenes/{creada['id']}/activate")

    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["payload"]["scene"] == {"id": creada["id"]}

        client.post("/api/v1/lights/power", json={"on": True})

        assert ws.receive_json()["type"] == "effect.stopped"
        snapshot = ws.receive_json()

    assert snapshot["type"] == "state.snapshot"
    assert snapshot["payload"]["scene"] is None


def test_activar_sin_enlace_responde_409(client: TestClient) -> None:
    """Sin `device` conectado: el enlace es lo primero que se comprueba."""
    respuesta_registro = client.post("/api/v1/devices", json={"name": "Tira", "address": ADDRESS})
    efecto = _crear_efecto(client, ESTATICO)
    creada = _crear_escena(client, _escena(respuesta_registro.json()["id"], efecto))

    response = client.post(f"/api/v1/scenes/{creada['id']}/activate")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "device_not_connected"


def test_activar_una_escena_sin_objetivos_responde_409(client: TestClient) -> None:
    creada = _crear_escena(client, {"name": "Vacia", "targets": []})

    response = client.post(f"/api/v1/scenes/{creada['id']}/activate")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "nothing_to_activate"


def test_activar_una_escena_inexistente_es_un_404(client: TestClient) -> None:
    response = client.post(f"/api/v1/scenes/{uuid4()}/activate")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "scene_not_found"


def test_un_efecto_con_pasos_insuficientes_responde_422_sin_activar_nada(
    client: TestClient, device: dict[str, Any]
) -> None:
    roto = _crear_efecto(
        client,
        {"name": "Ciclo de un color", "type": "SMOOTH_CYCLE", "steps": [{"color": "#009DFF"}]},
    )
    creada = _crear_escena(client, _escena(device["id"], roto))

    response = client.post(f"/api/v1/scenes/{creada['id']}/activate")

    assert response.status_code == 422
    assert client.get("/api/v1/state").json()["scene"] is None


def test_activar_una_escena_no_escribe_en_device_state(
    client: TestClient, settings: Settings, device: dict[str, Any]
) -> None:
    """Cero escrituras durante la reproduccion (ARCHITECTURE 4.5, NEXT_STEPS 6.7)."""
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, CICLO)))
    antes = _estado_de_dispositivos(settings)

    client.post(f"/api/v1/scenes/{creada['id']}/activate")

    assert _estado_de_dispositivos(settings) == antes


def test_scene_activated_llega_por_el_websocket(client: TestClient, device: dict[str, Any]) -> None:
    """Lo publica la capa de APLICACION; el motor no conoce el socket."""
    creada = _crear_escena(client, _escena(device["id"], _crear_efecto(client, CICLO)))

    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "state.snapshot"

        client.post(f"/api/v1/scenes/{creada['id']}/activate")
        arranque = ws.receive_json()
        activada = ws.receive_json()

    assert arranque["type"] == "effect.started"
    assert activada["type"] == "scene.activated"
    assert activada["payload"] == {"scene_id": creada["id"]}
    assert activada["version"] > arranque["version"]


def test_las_rutas_de_escenas_estan_en_el_openapi(client: TestClient) -> None:
    rutas = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/scenes" in rutas
    assert "/api/v1/scenes/{scene_id}" in rutas
    assert "/api/v1/scenes/{scene_id}/duplicate" in rutas
    assert "/api/v1/scenes/{scene_id}/activate" in rutas


def _estado_de_dispositivos(settings: Settings) -> tuple[int, list[tuple[str, int, str]]]:
    """Cuantas filas hay en `device_state` y que dicen, con un engine aparte."""
    engine = create_database_engine(settings.database)
    try:
        with Session(engine) as session:
            total = session.exec(select(func.count()).select_from(DeviceStateRecord)).one()
            filas = session.exec(select(DeviceStateRecord)).all()
            return total, [(row.color_hex, row.brightness, str(row.updated_at)) for row in filas]
    finally:
        engine.dispose()
