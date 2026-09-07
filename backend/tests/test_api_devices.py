"""Rutas de dispositivos, con el adaptador y el descubridor sin hardware.

Nada de esto necesita radio Bluetooth: el adaptador por defecto es el nulo y el
descubrimiento se sustituye con `dependency_overrides` cuando hace falta que un
escaneo devuelva algo.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from bleak.exc import BleakBluetoothNotAvailableError, BleakBluetoothNotAvailableReason
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.api import deps
from backend.app.config import Settings
from backend.app.domain.devices.models import DeviceTarget, DeviceType, DiscoveredDevice
from backend.app.domain.devices.ports import DeviceDiscoveryPort, DeviceError, LightDevicePort
from backend.app.infrastructure.bluetooth.scanner import Advertisements, BleDeviceScanner
from backend.app.infrastructure.devices import registry
from backend.app.infrastructure.devices.null_discovery import NullDiscoveryAdapter
from backend.app.main import create_app
from backend.tests.doubles import RecordingLightDevice, SlowDiscovery, api_settings

ADDRESS = "BE:FF:00:11:22:33"
OTHER_ADDRESS = "BE:FF:00:11:22:34"


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


def _register(client: TestClient, *, address: str = ADDRESS, name: str = "Tira") -> dict[str, Any]:
    response = client.post("/api/v1/devices", json={"name": name, "address": address})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _override_discovery(app: FastAPI, discovery: DeviceDiscoveryPort) -> None:
    app.dependency_overrides[deps.get_discovery] = lambda: discovery


def test_sin_dispositivos_registrados_la_lista_esta_vacia(client: TestClient) -> None:
    response = client.get("/api/v1/devices")

    assert response.status_code == 200
    assert response.json() == []


def test_registrar_un_dispositivo_devuelve_201_y_lo_deja_listado(client: TestClient) -> None:
    created = _register(client)

    assert created["name"] == "Tira"
    assert created["address"] == ADDRESS
    assert created["adapter_type"] == "null"
    assert created["connected"] is False
    assert created["capabilities"]["rgb"] is True
    # El identificador viaja como cadena, nunca como objeto UUID.
    assert isinstance(created["id"], str)

    listed = client.get("/api/v1/devices").json()
    assert [device["id"] for device in listed] == [created["id"]]


def test_registrar_dos_veces_la_misma_direccion_no_duplica_el_dispositivo(
    client: TestClient,
) -> None:
    """El registro es idempotente por direccion y conserva el id original."""
    first = _register(client, name="Tira")
    second = _register(client, name="Tira del salon")

    assert second["id"] == first["id"]
    assert second["name"] == "Tira del salon"
    assert len(client.get("/api/v1/devices").json()) == 1


def test_registrar_con_un_adaptador_que_contradice_la_configuracion_es_422(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/devices",
        json={"address": ADDRESS, "adapter_type": "lotus_lantern"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_payload"


def test_un_dispositivo_inexistente_devuelve_404_con_codigo_estable(client: TestClient) -> None:
    response = client.get(f"/api/v1/devices/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "device_not_found"


def test_un_identificador_mal_formado_devuelve_422(client: TestClient) -> None:
    response = client.get("/api/v1/devices/no-soy-un-uuid")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_payload"


def test_conectar_marca_el_dispositivo_como_conectado(client: TestClient) -> None:
    device = _register(client)

    connected = client.post(f"/api/v1/devices/{device['id']}/connect")

    assert connected.status_code == 200
    assert connected.json()["connected"] is True
    assert client.get(f"/api/v1/devices/{device['id']}").json()["connected"] is True
    assert client.get("/api/v1/state").json()["device"]["connected"] is True


def test_desconectar_es_idempotente(client: TestClient) -> None:
    device = _register(client)
    client.post(f"/api/v1/devices/{device['id']}/connect")

    first = client.post(f"/api/v1/devices/{device['id']}/disconnect")
    second = client.post(f"/api/v1/devices/{device['id']}/disconnect")

    assert first.status_code == second.status_code == 200
    assert first.json()["connected"] is False
    assert second.json()["connected"] is False


def test_conectar_un_dispositivo_inexistente_devuelve_404(client: TestClient) -> None:
    response = client.post(f"/api/v1/devices/{uuid4()}/connect")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "device_not_found"


def test_conectar_un_segundo_dispositivo_con_el_enlace_ocupado_devuelve_409(
    client: TestClient,
) -> None:
    """El proceso mantiene UN enlace: el segundo secuestraria al primero."""
    first = _register(client, address=ADDRESS, name="Salon")
    second = _register(client, address=OTHER_ADDRESS, name="Dormitorio")
    client.post(f"/api/v1/devices/{first['id']}/connect")

    response = client.post(f"/api/v1/devices/{second['id']}/connect")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "device_busy"


def test_escanear_sin_radio_devuelve_una_lista_vacia(client: TestClient) -> None:
    response = client.get("/api/v1/devices/scan")

    assert response.status_code == 200
    assert response.json() == []


def test_el_escaneo_devuelve_lo_descubierto_sin_identificador(
    app: FastAPI, client: TestClient
) -> None:
    _override_discovery(
        app,
        NullDiscoveryAdapter([DiscoveredDevice(name="ELK-BLEDOM", address=ADDRESS, rssi=-51)]),
    )

    response = client.get("/api/v1/devices/scan")

    assert response.status_code == 200
    assert response.json() == [{"name": "ELK-BLEDOM", "address": ADDRESS, "rssi": -51}]


def test_sin_bluetooth_el_escaneo_responde_503_con_una_causa_accionable(
    app: FastAPI, client: TestClient
) -> None:
    """El fallo que el adaptador sin radio no podia provocar (NEXT_STEPS A5/A6).

    Hasta que existio un escaner real, "este host no tiene Bluetooth" y "el
    escaneo expiro" salian los dos como `502 device_write_failed` y el cliente
    tenia que enumerar las posibilidades. Con la radio apagada la causa es
    conocida, y el usuario puede arreglarla.
    """

    async def sin_radio(timeout_s: float) -> Advertisements:
        raise BleakBluetoothNotAvailableError(
            "Bluetooth radio is not powered on",
            BleakBluetoothNotAvailableReason.POWERED_OFF,
        )

    _override_discovery(app, BleDeviceScanner(discover=sin_radio))

    response = client.get("/api/v1/devices/scan")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "device_unavailable"
    assert "apagado" in detail["message"]
    assert "traceback" not in response.text.lower()


def test_lo_descubierto_por_ble_se_registra_como_ble_aunque_el_control_sea_null(
    tmp_path: Path,
) -> None:
    """La familia que etiqueta es la que DESCUBRE.

    `get_by_address` resuelve solo por direccion y `POST /devices` es idempotente:
    una tira BLE guardada como `null` se reutilizaria mal etiquetada para siempre,
    incluso despues de activar el adaptador de control de la Fase 1.
    """
    settings = api_settings(tmp_path).model_copy(
        update={"device_discovery": DeviceType.LOTUS_LANTERN}
    )

    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/devices",
            json={"name": "Tira", "address": ADDRESS, "adapter_type": "lotus_lantern"},
        )

    assert created.status_code == 201, created.text
    assert created.json()["adapter_type"] == "lotus_lantern"


def test_el_timeout_pedido_nunca_supera_al_configurado(app: FastAPI, client: TestClient) -> None:
    discovery = SlowDiscovery(delay_s=0.0)
    _override_discovery(app, discovery)

    client.get("/api/v1/devices/scan", params={"timeout": 999})
    client.get("/api/v1/devices/scan", params={"timeout": 2})

    assert discovery.timeouts == [10.0, 2.0]


def test_un_timeout_no_positivo_se_rechaza_con_422(client: TestClient) -> None:
    response = client.get("/api/v1/devices/scan", params={"timeout": 0})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_payload"


@asynccontextmanager
async def _running(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Arranca el `lifespan` a mano: `ASGITransport` no lo ejecuta.

    Hace falta un cliente asincrono de verdad para que dos peticiones se solapen
    en el mismo bucle de eventos; con `TestClient` cada llamada es bloqueante.
    """
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_un_segundo_escaneo_simultaneo_devuelve_409(settings: Settings) -> None:
    app = create_app(settings)
    _override_discovery(app, SlowDiscovery(delay_s=0.05))

    async with _running(app) as client:
        first, second = await asyncio.gather(
            client.get("/api/v1/devices/scan"),
            client.get("/api/v1/devices/scan"),
        )

    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 409]
    rejected = first if first.status_code == 409 else second
    assert rejected.json()["detail"]["code"] == "device_busy"


@pytest.mark.asyncio
async def test_el_turno_de_escaneo_se_libera_al_terminar(settings: Settings) -> None:
    """Un 409 permanente seria peor que no tener guardia."""
    app = create_app(settings)
    _override_discovery(app, SlowDiscovery(delay_s=0.0))

    async with _running(app) as client:
        first = await client.get("/api/v1/devices/scan")
        second = await client.get("/api/v1/devices/scan")

    assert first.status_code == second.status_code == 200


class UnreachableDevice(RecordingLightDevice):
    """El controlador no responde: apagado, fuera de alcance o sin radio."""

    async def connect(self, target: DeviceTarget) -> None:
        raise DeviceError("no se encontro el controlador")


def test_el_servicio_arranca_aunque_el_dispositivo_no_conecte(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hardware ausente = arranque degradado, no caida (ARCHITECTURE 7.5)."""
    with TestClient(create_app(settings)) as client:
        device = _register(client)

    def unreachable(_: Settings) -> LightDevicePort:
        return UnreachableDevice()

    monkeypatch.setattr(main, "build_light_device", unreachable)

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").status_code == 200
        state = client.get("/api/v1/state").json()

    # `last_error` es el CODIGO estable, no el texto del fallo: viaja a todos
    # los clientes sin autenticacion, y en la Fase 1 lo escribira Bleak, cuyos
    # mensajes incluyen la direccion del controlador y rutas de D-Bus.
    assert state["device"] == {
        "device_id": device["id"],
        "connected": False,
        "rssi": None,
        "last_error": "device_write_failed",
    }
    assert "no se encontro el controlador" not in client.get("/api/v1/state").text


def test_el_adaptador_ble_ya_no_impide_arrancar(settings: Settings) -> None:
    """Con el protocolo verificado, `lotus_lantern` es una configuracion valida.

    Antes reventaba en el arranque con `NotImplementedError`. Arrancar no toca
    la radio: el enlace solo se abre al conectar un dispositivo.
    """
    lotus = settings.model_copy(update={"device_adapter": DeviceType.LOTUS_LANTERN})

    with TestClient(create_app(lotus)) as client:
        assert client.get("/api/v1/health").status_code == 200


def test_un_adaptador_sin_constructor_sigue_impidiendo_arrancar(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La otra mitad de la asimetria, que sigue vigente: lo que no existe es fatal.

    Arrancar igual solo aplazaria el error hasta la primera peticion, con
    `/health` mintiendo en 200 mientras tanto. Ya no se puede provocar con
    `lotus_lantern` -- ahora existe --, asi que se provoca vaciando el registro,
    que es la situacion real del dia que alguien añada una familia al enum y
    olvide su constructor.
    """
    monkeypatch.setitem(registry.ADAPTERS, DeviceType.NULL, None)

    with pytest.raises(AttributeError), TestClient(create_app(settings)):
        pass  # pragma: no cover - el fallo ocurre al entrar en el contexto
