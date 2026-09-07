"""Endpoint `/ws`: hidratacion, difusion y errores que no tumban la sesion.

Sin hardware: el adaptador nulo cumple el puerto y el limitador de color usa el
intervalo real de la configuracion (50 ms), que es corto y no vuelve lentos los
tests.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session
from starlette.testclient import WebSocketTestSession

from backend.app import main
from backend.app.api.deps import resources_of
from backend.app.config import Settings
from backend.app.domain.devices.ports import LightDevicePort
from backend.app.infrastructure.persistence.database import create_database_engine
from backend.app.infrastructure.persistence.models.device import DeviceStateRecord
from backend.app.main import create_app
from backend.app.websocket.events import _PARSERS, CommandType
from backend.tests.doubles import RecordingLightDevice, api_settings

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


@pytest.fixture
def connected(client: TestClient) -> dict[str, Any]:
    device: dict[str, Any] = client.post(
        "/api/v1/devices", json={"name": "Tira", "address": ADDRESS}
    ).json()
    client.post(f"/api/v1/devices/{device['id']}/connect")
    return device


def _hydrate(websocket: WebSocketTestSession) -> dict[str, Any]:
    """Consume el snapshot inicial y lo devuelve."""
    frame: dict[str, Any] = websocket.receive_json()
    assert frame["type"] == "state.snapshot"
    return frame


def test_todo_frame_del_servidor_lleva_la_version_en_el_sobre(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """B2: sin este numero, un hueco de eventos es indetectable para el cliente.

    Los hay por diseño: una conexion fallida gasta version sin publicar evento, y
    la cola de salida de un cliente lento descarta frames. Con la version en el
    sobre, el cliente ve el salto y rehidrata con `GET /api/v1/state`.
    """
    with client.websocket_connect("/ws") as websocket:
        snapshot = _hydrate(websocket)

        websocket.send_json({"type": "light.power", "payload": {"on": True}})
        cambio = websocket.receive_json()

        websocket.send_json({"type": "light.power", "payload": {"on": "quiza"}})
        error = websocket.receive_json()

    assert snapshot["version"] == snapshot["payload"]["version"]
    assert cambio["version"] == snapshot["version"] + 1
    # El error no cambia el estado: repite la version, y eso es justamente lo
    # que le dice al cliente que no se perdio nada.
    assert error["type"] == "error"
    assert error["version"] == cambio["version"]


def test_el_frame_de_error_del_socket_resume_igual_que_rest(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """I7: la politica de errores dice ser la misma para los dos transportes.

    Antes, por socket salia el `str()` crudo de Pydantic (multilinea y con la URL
    de su version) y por REST un resumen legible.
    """
    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)
        websocket.send_json({"type": "light.color", "payload": {"r": 300, "g": 0, "b": 0}})
        mensaje = websocket.receive_json()["payload"]["message"]

    rest = client.put("/api/v1/lights/color", json={"r": 300, "g": 0, "b": 0})

    assert mensaje == rest.json()["detail"]["message"]
    assert mensaje.splitlines() == [mensaje], "El volcado crudo de Pydantic es multilinea"
    assert "pydantic.dev" not in mensaje
    assert mensaje.startswith("r: ")


def test_el_primer_mensaje_es_el_estado_completo(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        frame = _hydrate(websocket)

    assert frame["payload"] == {
        "version": 0,
        "device": None,
        "light": {"power": False, "color": "#FFFFFF", "brightness": 100},
        "effect": None,
        "scene": None,
    }


def test_el_snapshot_del_socket_es_el_mismo_cuerpo_que_el_de_rest(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """Una sola forma para hidratar por REST y por WebSocket (NEXT_STEPS A4)."""
    with client.websocket_connect("/ws") as websocket:
        frame = _hydrate(websocket)

    assert frame["payload"] == client.get("/api/v1/state").json()


def test_el_snapshot_solo_llega_a_quien_acaba_de_conectar(
    client: TestClient, connected: dict[str, Any]
) -> None:
    with client.websocket_connect("/ws") as first:
        _hydrate(first)

        with client.websocket_connect("/ws") as second:
            _hydrate(second)

            # Si el snapshot del segundo se hubiera difundido, este seria el
            # mensaje que leyera el primero en vez de su propio cambio.
            second.send_json({"type": "light.power", "payload": {"on": True}})
            assert first.receive_json()["type"] == "light.power.changed"


def test_el_cambio_de_un_cliente_llega_a_los_demas(
    client: TestClient, connected: dict[str, Any]
) -> None:
    with client.websocket_connect("/ws") as sender, client.websocket_connect("/ws") as observer:
        _hydrate(sender)
        _hydrate(observer)

        sender.send_json({"type": "light.power", "payload": {"on": True}})

        # Tambien al emisor: es lo que corrige a un cliente optimista si el
        # comando se recorta o el hardware lo rechaza.
        esperado = {"type": "light.power.changed", "version": 2, "payload": {"power": True}}
        assert sender.receive_json() == esperado
        assert observer.receive_json() == esperado


def test_el_color_se_difunde_en_hexadecimal_mayusculas(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """El evento de dominio lleva `RGBColor`; serializarlo es cosa del transporte."""
    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)

        websocket.send_json({"type": "light.color", "payload": {"r": 123, "g": 0, "b": 255}})

        assert websocket.receive_json() == {
            "type": "light.color.changed",
            "version": 2,
            "payload": {"color": "#7B00FF"},
        }


def test_el_brillo_por_socket_actualiza_el_estado_global(
    client: TestClient, connected: dict[str, Any]
) -> None:
    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)

        websocket.send_json({"type": "light.brightness", "payload": {"brightness": 35}})

        assert websocket.receive_json() == {
            "type": "light.brightness.changed",
            "version": 2,
            "payload": {"brightness": 35},
        }

    assert client.get("/api/v1/state").json()["light"]["brightness"] == 35


def test_un_mensaje_invalido_devuelve_error_y_no_cierra_el_socket(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """Un arrastre del selector de color no puede tirar la sesion."""
    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)

        websocket.send_json({"type": "light.color", "payload": {"r": 300, "g": 0, "b": 0}})
        error = websocket.receive_json()

        assert error["type"] == "error"
        assert error["payload"]["code"] == "invalid_payload"

        # La sesion sigue viva: el siguiente comando se atiende con normalidad.
        websocket.send_json({"type": "light.power", "payload": {"on": True}})
        assert websocket.receive_json()["type"] == "light.power.changed"


def test_un_texto_que_no_es_json_devuelve_error(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)

        websocket.send_text("{no soy json")

        assert websocket.receive_json()["payload"]["code"] == "invalid_payload"


def test_un_tipo_de_mensaje_desconocido_devuelve_error(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)

        websocket.send_json({"type": "light.teleport", "payload": {}})
        error = websocket.receive_json()

        assert error["payload"]["code"] == "invalid_payload"
        assert "light.teleport" in error["payload"]["message"]


def test_un_frame_binario_devuelve_error_y_no_un_fallo_interno(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)

        websocket.send_bytes(b"\x7e\x00\x05")

        assert websocket.receive_json()["payload"]["code"] == "invalid_payload"


def test_un_comando_sin_dispositivo_conectado_devuelve_error(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)

        websocket.send_json({"type": "light.power", "payload": {"on": True}})
        error = websocket.receive_json()

        assert error["type"] == "error"
        assert error["payload"]["code"] == "device_not_connected"


def test_un_fallo_del_arrastre_de_color_tambien_se_notifica(client: TestClient) -> None:
    """El limitador aplica desde una tarea de fondo: sin esto, el fallo moriria en el log."""
    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)

        websocket.send_json({"type": "light.color", "payload": {"r": 1, "g": 2, "b": 3}})
        error = websocket.receive_json()

        assert error["type"] == "error"
        assert error["payload"]["code"] == "device_not_connected"


def test_las_conexiones_se_registran_al_aceptarlas(app: FastAPI, client: TestClient) -> None:
    manager = resources_of(app).connections
    assert manager.count == 0

    with client.websocket_connect("/ws") as first:
        _hydrate(first)
        assert manager.count == 1

        with client.websocket_connect("/ws") as second:
            _hydrate(second)
            assert manager.count == 2


def test_la_desconexion_de_un_cliente_no_rompe_la_difusion(
    app: FastAPI, client: TestClient, connected: dict[str, Any]
) -> None:
    """El que se va no puede llevarse por delante al que se queda.

    Aqui el cliente se cierra ANTES de la difusion, asi que esto comprueba la
    baja y que el reparto siga funcionando con una conexion menos -- no el
    reparto sobre un socket ya muerto. Ese caso no se puede provocar de forma
    determinista con `TestClient` (no hay manera de retener el
    `websocket.disconnect` del servidor), y por eso vive en
    `test_connection_manager.py::test_un_socket_que_ya_cerro_se_descarta_sin_romper_la_difusion`,
    donde el doble falla el envio a voluntad.
    """
    manager = resources_of(app).connections

    with client.websocket_connect("/ws") as survivor:
        _hydrate(survivor)

        with client.websocket_connect("/ws") as leaving:
            _hydrate(leaving)
            assert manager.count == 2

        survivor.send_json({"type": "light.power", "payload": {"on": True}})

        assert survivor.receive_json()["type"] == "light.power.changed"
        assert manager.count == 1


def test_conectar_un_dispositivo_difunde_el_estado_completo(
    client: TestClient, connected: dict[str, Any]
) -> None:
    """`device.connected` solo lleva el id; sin el snapshot, los demas clientes
    seguirian mostrando la luz anterior a la rehidratacion."""
    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)

        client.post(f"/api/v1/devices/{connected['id']}/disconnect")
        assert websocket.receive_json()["type"] == "device.disconnected"

        client.post(f"/api/v1/devices/{connected['id']}/connect")

        frame = websocket.receive_json()
        assert frame["type"] == "device.connected"
        assert frame["payload"] == {"device_id": connected["id"]}
        assert websocket.receive_json()["type"] == "state.snapshot"


def test_todo_comando_declarado_tiene_quien_lo_interprete() -> None:
    """Añadir un miembro a `CommandType` y olvidar su parser debe romper la build."""
    assert set(CommandType) == set(_PARSERS)


def _stored_state(settings: Settings, device_id: str) -> DeviceStateRecord | None:
    """Lee la fila `device_state` con un engine aparte, como lo haria un reinicio."""
    engine = create_database_engine(settings.database)
    try:
        with Session(engine) as session:
            return session.get(DeviceStateRecord, UUID(device_id))
    finally:
        engine.dispose()


def test_el_socket_no_persiste_nada(
    client: TestClient, connected: dict[str, Any], settings: Settings
) -> None:
    """La regla que separa `/ws` de `/api/v1/lights` (NEXT_STEPS A3).

    El socket transporta el ARRASTRE, y un arrastre no es una intencion cerrada:
    escribir en la base por fotograma convertiria un gesto en decenas de
    `commit()`. La intencion la delimita una peticion HTTP, y por eso la
    persistencia vive alli.
    """
    assert _stored_state(settings, connected["id"]) is None

    with client.websocket_connect("/ws") as websocket:
        _hydrate(websocket)

        for value in range(10):
            websocket.send_json({"type": "light.color", "payload": {"r": value, "g": 0, "b": 0}})
        websocket.send_json({"type": "light.brightness", "payload": {"brightness": 42}})
        websocket.send_json({"type": "light.power", "payload": {"on": True}})

        time.sleep(0.4)

    assert client.get("/api/v1/state").json()["light"]["power"] is True, (
        "El estado en memoria SI cambia: lo que no cambia es la base"
    )
    assert _stored_state(settings, connected["id"]) is None


def test_el_arrastre_por_socket_pasa_de_verdad_por_los_limitadores(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cablear el limitador y saltarselo dan los mismos eventos: solo el adaptador lo nota.

    Sin este test, cambiar `_dispatch` para llamar a `set_color` / `set_brightness`
    directamente dejaba la suite entera en verde y mandaba una escritura BLE por
    cada evento del arrastre.
    """
    device = RecordingLightDevice()

    def fake(_: Settings) -> LightDevicePort:
        return device

    monkeypatch.setattr(main, "build_light_device", fake)

    frames = 60
    with TestClient(create_app(settings)) as client:
        registered = client.post("/api/v1/devices", json={"name": "Tira", "address": ADDRESS})
        device_id = registered.json()["id"]
        client.post(f"/api/v1/devices/{device_id}/connect")
        del device.writes[:]  # la reconciliacion del connect no cuenta

        with client.websocket_connect("/ws") as websocket:
            _hydrate(websocket)
            for value in range(frames):
                websocket.send_json(
                    {"type": "light.color", "payload": {"r": value, "g": 0, "b": 0}}
                )
                websocket.send_json({"type": "light.brightness", "payload": {"brightness": value}})
            time.sleep(0.5)

    colores = [op for op in device.operations if op.startswith("set_color")]
    brillos = [op for op in device.operations if op.startswith("set_brightness")]

    assert 0 < len(colores) < frames // 2, f"{len(colores)} escrituras de color de {frames}"
    assert 0 < len(brillos) < frames // 2, f"{len(brillos)} escrituras de brillo de {frames}"
    # Borde de salida: el ultimo valor del arrastre se aplica SIEMPRE, o la tira
    # se queda en un color que el usuario ya solto.
    assert colores[-1] == f"set_color:{frames - 1},0,0"
    assert brillos[-1] == f"set_brightness:{frames - 1}"
