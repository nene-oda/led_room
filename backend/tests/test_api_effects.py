"""Rutas de efectos: CRUD, reproduccion y la politica de errores compartida.

Se prueba la aplicacion entera, con el adaptador nulo y una base temporal: es la
unica forma de comprobar que un 409 del dominio sale con el cuerpo uniforme y
que reproducir no escribe en la base.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.config import Settings
from backend.app.infrastructure.persistence.database import create_database_engine
from backend.app.infrastructure.persistence.models.device import DeviceStateRecord
from backend.app.main import create_app
from backend.tests.doubles import api_settings

ADDRESS = "BE:FF:00:11:22:33"

CYBERPUNK: dict[str, Any] = {
    "name": "Cyberpunk",
    "type": "SMOOTH_CYCLE",
    "loop": True,
    "speed": 40,
    "fps": 15,
    "transition_ms": 3500,
    "steps": [
        {"color": "#009DFF"},
        {"color": "#7b00ff"},
        {"color": "#FF008C"},
    ],
}

ESTATICO: dict[str, Any] = {
    "name": "Salon",
    "type": "STATIC",
    "steps": [{"color": "#7B00FF", "brightness": 60}],
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
def connected(client: TestClient) -> dict[str, Any]:
    """Un dispositivo registrado y con el enlace abierto."""
    created = client.post("/api/v1/devices", json={"name": "Tira", "address": ADDRESS})
    device: dict[str, Any] = created.json()
    assert client.post(f"/api/v1/devices/{device['id']}/connect").status_code == 200
    return device


def _crear(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/v1/effects", json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def test_el_catalogo_arranca_vacio(client: TestClient) -> None:
    """Una base recien migrada no se siembra con efectos (NEXT_STEPS 6.1)."""
    response = client.get("/api/v1/effects")

    assert response.status_code == 200
    assert response.json() == []


def test_crear_un_efecto_devuelve_201_con_su_identidad(client: TestClient) -> None:
    creado = _crear(client, CYBERPUNK)

    assert creado["name"] == "Cyberpunk"
    assert creado["is_builtin"] is False
    assert [step["position"] for step in creado["steps"]] == [0, 1, 2]


def test_el_color_de_un_paso_se_devuelve_en_mayusculas(client: TestClient) -> None:
    """Se acepta `#7b00ff` al escribir y se publica `#7B00FF` (ARCHITECTURE 3.2)."""
    creado = _crear(client, CYBERPUNK)

    assert [step["color"] for step in creado["steps"]] == ["#009DFF", "#7B00FF", "#FF008C"]


def test_un_efecto_creado_se_lee_y_se_lista(client: TestClient) -> None:
    creado = _crear(client, CYBERPUNK)

    leido = client.get(f"/api/v1/effects/{creado['id']}")
    listado = client.get("/api/v1/effects")

    assert leido.status_code == 200
    assert leido.json() == creado
    assert listado.json() == [creado]


def test_reemplazar_un_efecto_conserva_su_identificador(client: TestClient) -> None:
    creado = _crear(client, CYBERPUNK)

    response = client.put(
        f"/api/v1/effects/{creado['id']}",
        json={**CYBERPUNK, "name": "Cyberpunk v2", "steps": [{"color": "#FF008C"}]},
    )

    assert response.status_code == 200
    assert response.json()["id"] == creado["id"]
    assert response.json()["name"] == "Cyberpunk v2"
    assert len(response.json()["steps"]) == 1


def test_reemplazar_un_efecto_inexistente_no_lo_crea(client: TestClient) -> None:
    """Un PUT sobre un id inventado crearia un efecto con id elegido por el cliente."""
    response = client.put(f"/api/v1/effects/{uuid4()}", json=CYBERPUNK)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "effect_not_found"
    assert client.get("/api/v1/effects").json() == []


def test_borrar_un_efecto_lo_quita_del_catalogo(client: TestClient) -> None:
    creado = _crear(client, CYBERPUNK)

    assert client.delete(f"/api/v1/effects/{creado['id']}").status_code == 204
    assert client.get(f"/api/v1/effects/{creado['id']}").status_code == 404


def test_borrar_algo_que_no_existe_responde_404(client: TestClient) -> None:
    response = client.delete(f"/api/v1/effects/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "effect_not_found"


def test_borrar_un_efecto_que_usa_una_escena_responde_409(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """409, no 500: el `RESTRICT` de `scene_targets` protege a la escena.

    Que el `IntegrityError` subiera crudo hasta el handler generico convertia un
    error del usuario en un fallo del servidor, y el mensaje generico de los 500
    no le decia que hacer.
    """
    creado = _crear(client, ESTATICO)
    escena = client.post(
        "/api/v1/scenes",
        json={
            "name": "Noche",
            "targets": [{"device_id": connected["id"], "effect_id": creado["id"]}],
        },
    )
    assert escena.status_code == 201, escena.text

    response = client.delete(f"/api/v1/effects/{creado['id']}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "effect_in_use"
    assert creado["id"] in response.json()["detail"]["message"]
    # Ni el efecto ni la escena se han quedado a medias.
    assert client.get(f"/api/v1/effects/{creado['id']}").status_code == 200
    assert len(client.get("/api/v1/scenes").json()) == 1


def test_borrar_un_efecto_liberado_por_su_escena_vuelve_a_funcionar(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """El 409 no deja la sesion rota: la siguiente peticion opera con normalidad."""
    creado = _crear(client, ESTATICO)
    escena = client.post(
        "/api/v1/scenes",
        json={
            "name": "Noche",
            "targets": [{"device_id": connected["id"], "effect_id": creado["id"]}],
        },
    ).json()
    assert client.delete(f"/api/v1/effects/{creado['id']}").status_code == 409

    assert client.delete(f"/api/v1/scenes/{escena['id']}").status_code == 204
    assert client.delete(f"/api/v1/effects/{creado['id']}").status_code == 204


@pytest.mark.parametrize(
    "campo",
    [
        {"speed": 101},
        {"fps": 0},
        {"transition_ms": -1},
        {"min_brightness": 101},
        {"steps": [{"color": "rojo"}]},
        {"type": "TELETRANSPORTE"},
    ],
)
def test_un_cuerpo_invalido_responde_422_con_el_cuerpo_uniforme(
    client: TestClient, campo: dict[str, Any]
) -> None:
    response = client.post("/api/v1/effects", json={**CYBERPUNK, **campo})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_payload"


def test_una_envolvente_invertida_la_rechaza_el_dominio(client: TestClient) -> None:
    response = client.post(
        "/api/v1/effects", json={**CYBERPUNK, "min_brightness": 80, "max_brightness": 20}
    )

    assert response.status_code == 422
    assert "min_brightness" in response.json()["detail"]["message"]


def test_guardar_un_efecto_no_exige_que_haya_dispositivo(client: TestClient) -> None:
    """Un efecto se guarda aunque hoy no haya nada que lo reproduzca."""
    assert client.post("/api/v1/effects", json=CYBERPUNK).status_code == 201


def test_sin_dispositivo_conectado_reproducir_responde_409(client: TestClient) -> None:
    creado = _crear(client, CYBERPUNK)

    response = client.post(f"/api/v1/effects/{creado['id']}/start")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "device_not_connected"


def test_reproducir_un_efecto_inexistente_responde_404(
    client: TestClient, connected: dict[str, Any]
) -> None:
    response = client.post(f"/api/v1/effects/{uuid4()}/start")

    assert response.status_code == 404


def test_un_efecto_sin_los_pasos_de_su_algoritmo_responde_422(
    client: TestClient, connected: dict[str, Any]
) -> None:
    creado = _crear(client, {**CYBERPUNK, "steps": [{"color": "#009DFF"}]})

    response = client.post(f"/api/v1/effects/{creado['id']}/start")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_payload"


def test_reproducir_deja_el_efecto_en_el_estado_global(
    client: TestClient, connected: dict[str, Any]
) -> None:
    creado = _crear(client, CYBERPUNK)

    response = client.post(f"/api/v1/effects/{creado['id']}/start")

    assert response.status_code == 200
    assert response.json() == {"running": True, "id": creado["id"]}

    estado = client.get("/api/v1/state").json()
    assert estado["effect"] == {"running": True, "id": creado["id"]}

    client.post(f"/api/v1/effects/{creado['id']}/stop")


def test_parar_vacia_la_ranura_del_estado_global(
    client: TestClient, connected: dict[str, Any]
) -> None:
    creado = _crear(client, CYBERPUNK)
    client.post(f"/api/v1/effects/{creado['id']}/start")

    response = client.post(f"/api/v1/effects/{creado['id']}/stop")

    assert response.status_code == 200
    assert response.json() is None
    assert client.get("/api/v1/state").json()["effect"] is None


def test_parar_algo_que_no_suena_es_idempotente(
    client: TestClient, connected: dict[str, Any]
) -> None:
    creado = _crear(client, CYBERPUNK)

    response = client.post(f"/api/v1/effects/{creado['id']}/stop")

    assert response.status_code == 200
    assert response.json() is None


def test_parar_un_efecto_ya_sustituido_devuelve_el_que_suena(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """Responder `null` aqui mentiria sobre el estado global."""
    viejo = _crear(client, CYBERPUNK)
    nuevo = _crear(client, {**CYBERPUNK, "name": "Gaming"})
    client.post(f"/api/v1/effects/{viejo['id']}/start")
    client.post(f"/api/v1/effects/{nuevo['id']}/start")

    response = client.post(f"/api/v1/effects/{viejo['id']}/stop")

    assert response.json() == {"running": True, "id": nuevo["id"]}

    client.post(f"/api/v1/effects/{nuevo['id']}/stop")


def test_un_comando_manual_de_color_cancela_el_efecto_en_curso(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """La preempcion tambien vale desde REST, no solo desde el WebSocket."""
    creado = _crear(client, CYBERPUNK)
    client.post(f"/api/v1/effects/{creado['id']}/start")

    response = client.put("/api/v1/lights/color", json={"r": 255, "g": 0, "b": 140})

    assert response.status_code == 200
    assert client.get("/api/v1/state").json()["effect"] is None


def test_reproducir_no_escribe_en_device_state(
    client: TestClient, settings: Settings, connected: dict[str, Any]
) -> None:
    """Cero escrituras por fotograma: la base no se toca durante un efecto."""
    creado = _crear(client, CYBERPUNK)
    antes = _marcas_de_estado(settings)

    client.post(f"/api/v1/effects/{creado['id']}/start")
    client.post(f"/api/v1/effects/{creado['id']}/stop")

    assert _marcas_de_estado(settings) == antes


def test_un_efecto_estatico_es_un_solo_paso(client: TestClient, connected: dict[str, Any]) -> None:
    """Resuelve el caso mas comun de escena: color fijo (Fase 6)."""
    creado = _crear(client, ESTATICO)

    response = client.post(f"/api/v1/effects/{creado['id']}/start")

    assert response.status_code == 200


def test_los_eventos_de_efecto_llegan_por_el_websocket(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """`effect.started` y `effect.stopped` los publica la capa de APLICACION.

    El motor no conoce el socket: llega hasta aqui porque el servicio muta el
    store y el store publica por `EventPublisher` (NEXT_STEPS 6.7).
    """
    creado = _crear(client, CYBERPUNK)

    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "state.snapshot"

        client.post(f"/api/v1/effects/{creado['id']}/start")
        arranque = ws.receive_json()

        client.post(f"/api/v1/effects/{creado['id']}/stop")
        parada = ws.receive_json()

    assert arranque["type"] == "effect.started"
    assert arranque["payload"] == {"effect_id": creado["id"]}
    assert parada["type"] == "effect.stopped"
    assert parada["version"] > arranque["version"]


def test_las_rutas_de_efectos_estan_en_el_openapi(client: TestClient) -> None:
    rutas = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/effects" in rutas
    assert "/api/v1/effects/{effect_id}/start" in rutas
    assert "/api/v1/effects/{effect_id}/stop" in rutas


def _marcas_de_estado(settings: Settings) -> list[tuple[str, int, str]]:
    """Fotografia de `device_state`, leida con un engine aparte."""
    engine = create_database_engine(settings.database)
    try:
        with Session(engine) as session:
            filas = session.exec(select(DeviceStateRecord)).all()
            return [(row.color_hex, row.brightness, str(row.updated_at)) for row in filas]
    finally:
        engine.dispose()
