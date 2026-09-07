"""Casos de uso de dispositivos: escaneo, registro y ciclo de vida del enlace.

Sin hardware y sin base de datos: el repositorio es el doble en memoria que
cumple el Protocol de dominio, y el descubridor es el adaptador nulo que ya
existe en produccion. Un "fake adapter" nuevo seria duplicar lo que ya hay.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from backend.app.application import device_service as device_service_module
from backend.app.application.device_service import DeviceService
from backend.app.application.errors import DeviceBusyError, DeviceNotFoundError
from backend.app.application.state_store import StateStore
from backend.app.domain.devices.models import (
    SINGLE_COLOR_STRIP,
    Device,
    DeviceStatus,
    DeviceTarget,
    DeviceType,
    DiscoveredDevice,
)
from backend.app.domain.devices.ports import DeviceDiscoveryPort, DeviceError
from backend.app.domain.events import EventType
from backend.app.domain.lighting import LightState, RGBColor
from backend.app.infrastructure.devices.null_discovery import NullDiscoveryAdapter
from backend.tests.doubles import (
    InMemoryDeviceRepository,
    RecordingEventPublisher,
    RecordingLightDevice,
)

FIXED_ID = UUID("11111111-2222-3333-4444-555555555555")
ADDRESS = "BE:FF:00:11:22:33"
PURPLE = RGBColor.from_hex("#7B00FF")


class HangingDiscovery:
    """Un escaner que nunca devuelve: la radio se quedo colgada."""

    async def scan(self, timeout_s: float) -> Sequence[DiscoveredDevice]:
        await asyncio.Event().wait()
        raise AssertionError("inalcanzable")  # pragma: no cover


class UnreachableDevice(RecordingLightDevice):
    """El controlador no responde al `connect()`: apagado o fuera de alcance."""

    async def connect(self, target: DeviceTarget) -> None:
        raise DeviceError("no se encontro el controlador")


class Fixture:
    """Todo lo que el servicio necesita, ya cableado."""

    def __init__(
        self,
        *,
        device: RecordingLightDevice | None = None,
        discovery: DeviceDiscoveryPort | None = None,
        scan_timeout_s: float = 10.0,
        devices: Sequence[Device] = (),
    ) -> None:
        self.device = device if device is not None else RecordingLightDevice()
        self.repository = InMemoryDeviceRepository(devices)
        self.publisher = RecordingEventPublisher()
        self.store = StateStore(self.publisher)
        self.service = DeviceService(
            repository=self.repository,
            discovery=discovery if discovery is not None else NullDiscoveryAdapter(),
            device=self.device,
            store=self.store,
            adapter_type=DeviceType.NULL,
            scan_timeout_s=scan_timeout_s,
            new_id=lambda: FIXED_ID,
        )


def _registered(**overrides: object) -> Device:
    values: dict[str, object] = {
        "id": FIXED_ID,
        "name": "Bedroom LED",
        "adapter_type": DeviceType.NULL,
        "address": ADDRESS,
        "capabilities": SINGLE_COLOR_STRIP,
    }
    values.update(overrides)
    return Device.model_validate(values)


class RecordingDiscovery:
    """Descubridor que anota con que timeout se le llamo."""

    def __init__(self, devices: Sequence[DiscoveredDevice] = ()) -> None:
        self.timeouts: list[float] = []
        self._devices = tuple(devices)

    async def scan(self, timeout_s: float) -> Sequence[DiscoveredDevice]:
        self.timeouts.append(timeout_s)
        return self._devices


@pytest.mark.asyncio
async def test_el_escaneo_delega_en_el_puerto_de_descubrimiento() -> None:
    found = DiscoveredDevice(name="ELK-BLEDOM", address=ADDRESS, rssi=-60)
    discovery = RecordingDiscovery([found])
    fixture = Fixture(discovery=discovery)

    result = await fixture.service.scan()

    assert list(result) == [found]
    assert discovery.timeouts == [10.0]


@pytest.mark.asyncio
async def test_el_cliente_puede_pedir_menos_tiempo_de_escaneo_pero_nunca_mas() -> None:
    """El limite del escaneo es una decision de despliegue, no del cliente."""
    discovery = RecordingDiscovery()
    fixture = Fixture(discovery=discovery, scan_timeout_s=10.0)

    await fixture.service.scan(timeout_s=3.0)
    await fixture.service.scan(timeout_s=99.0)

    assert discovery.timeouts == [3.0, 10.0]


@pytest.mark.asyncio
async def test_un_escaner_colgado_produce_un_error_de_dispositivo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ninguna capa superior debe conocer `asyncio.TimeoutError` (NEXT_STEPS A6)."""
    monkeypatch.setattr(device_service_module, "SCAN_GRACE_S", 0.01)
    fixture = Fixture(discovery=HangingDiscovery(), scan_timeout_s=0.01)

    with pytest.raises(DeviceError, match="no termino"):
        await fixture.service.scan()


@pytest.mark.asyncio
async def test_un_timeout_de_escaneo_no_positivo_es_invalido() -> None:
    fixture = Fixture()

    with pytest.raises(ValueError, match="positivo"):
        await fixture.service.scan(timeout_s=0)


def test_registrar_genera_el_uuid_en_el_servidor_y_hereda_las_capacidades() -> None:
    """El cliente no puede inventar la identidad de algo que acaba de descubrir."""
    fixture = Fixture()

    device = fixture.service.register(DiscoveredDevice(name="ELK-BLEDOM", address=ADDRESS))

    assert device.id == FIXED_ID
    assert device.name == "ELK-BLEDOM"
    assert device.address == ADDRESS
    assert device.adapter_type is DeviceType.NULL
    assert device.capabilities == SINGLE_COLOR_STRIP
    assert fixture.repository.get(FIXED_ID) == device


def test_un_controlador_sin_nombre_anunciado_se_registra_con_su_direccion() -> None:
    """Muchos controladores de esta clase se anuncian sin nombre."""
    fixture = Fixture()

    device = fixture.service.register(DiscoveredDevice(address=ADDRESS))

    assert device.name == ADDRESS


def test_el_nombre_pedido_por_el_usuario_gana_al_anunciado() -> None:
    fixture = Fixture()

    device = fixture.service.register(
        DiscoveredDevice(name="ELK-BLEDOM", address=ADDRESS), name="Salon"
    )

    assert device.name == "Salon"


def test_registrar_dos_veces_la_misma_direccion_no_duplica_ni_cambia_el_id() -> None:
    """El id que manda es el que devuelve el repositorio (oleada 2B)."""
    fixture = Fixture(devices=[_registered(id=uuid4(), name="Bedroom LED")])
    original = next(iter(fixture.repository.devices.values()))

    again = fixture.service.register(DiscoveredDevice(name="ELK-BLEDOM", address=ADDRESS))

    assert again.id == original.id != FIXED_ID
    assert again.name == "Bedroom LED", "Re-registrar no renombra si nadie pidio otro nombre"
    assert len(fixture.repository.devices) == 1


def test_listar_devuelve_solo_los_dispositivos_habilitados() -> None:
    fixture = Fixture(
        devices=[
            _registered(id=uuid4(), name="Salon", address="AA:00"),
            _registered(id=uuid4(), name="Trastero", address="BB:00", enabled=False),
        ]
    )

    assert [device.name for device in fixture.service.list_devices()] == ["Salon"]


def test_pedir_un_dispositivo_desconocido_es_un_error_de_aplicacion() -> None:
    fixture = Fixture()

    with pytest.raises(DeviceNotFoundError):
        fixture.service.get_device(uuid4())


@pytest.mark.asyncio
async def test_conectar_reconcilia_el_hardware_con_el_estado_deseado_persistido() -> None:
    """El hardware puede estar en cualquier estado; el store no le pregunta."""
    fixture = Fixture(devices=[_registered()])
    fixture.repository.states[FIXED_ID] = LightState(power=True, color=PURPLE, brightness=30)

    status = await fixture.service.connect(FIXED_ID)

    assert status == DeviceStatus(device_id=FIXED_ID, connected=True)
    assert fixture.device.connect_calls == 1
    assert fixture.device.operations == [
        "set_power:True",
        "set_color:123,0,255",
        "set_brightness:30",
    ]

    state = await fixture.store.snapshot()
    assert state.light.color == PURPLE
    assert state.device == status


@pytest.mark.asyncio
async def test_conectar_publica_device_connected_y_despues_el_estado_completo() -> None:
    """`device.connected` solo lleva el id: sin el snapshot, los demas clientes se quedan atras."""
    fixture = Fixture(devices=[_registered()])
    fixture.repository.states[FIXED_ID] = LightState(power=True, color=PURPLE, brightness=30)

    await fixture.service.connect(FIXED_ID)

    assert fixture.publisher.types == [
        EventType.DEVICE_CONNECTED.value,
        EventType.STATE_SNAPSHOT.value,
    ]


@pytest.mark.asyncio
async def test_sin_estado_persistido_se_reconcilia_con_los_valores_por_defecto() -> None:
    fixture = Fixture(devices=[_registered()])

    await fixture.service.connect(FIXED_ID)

    assert (await fixture.store.snapshot()).light == LightState()


@pytest.mark.asyncio
async def test_conectar_un_id_desconocido_no_toca_el_dispositivo() -> None:
    fixture = Fixture()

    with pytest.raises(DeviceNotFoundError):
        await fixture.service.connect(uuid4())

    assert fixture.device.connect_calls == 0


@pytest.mark.asyncio
async def test_conectar_un_segundo_dispositivo_sin_soltar_el_primero_es_un_conflicto() -> None:
    """El proceso mantiene UN enlace: el segundo secuestraria al primero."""
    other = _registered(id=uuid4(), name="Salon", address="AA:00")
    fixture = Fixture(devices=[_registered(), other])
    await fixture.service.connect(FIXED_ID)
    fixture.device.writes.clear()

    with pytest.raises(DeviceBusyError):
        await fixture.service.connect(other.id)

    assert fixture.device.writes == []
    assert (await fixture.store.snapshot()).device == DeviceStatus(
        device_id=FIXED_ID, connected=True
    )


@pytest.mark.asyncio
async def test_un_connect_fallido_propaga_el_error_y_deja_constancia_en_el_estado() -> None:
    fixture = Fixture(device=UnreachableDevice(), devices=[_registered()])

    with pytest.raises(DeviceError, match="no se encontro"):
        await fixture.service.connect(FIXED_ID)

    status = (await fixture.store.snapshot()).device
    assert status is not None
    assert status.connected is False
    # El CODIGO estable, no el texto: `last_error` se difunde a todos los
    # clientes y el texto de un fallo del transporte filtra direcciones y rutas.
    assert status.last_error == "device_write_failed"
    assert fixture.publisher.events == [], "Un intento fallido no describe ningun evento congelado"


@pytest.mark.asyncio
async def test_un_fallo_al_reconciliar_tambien_deja_el_dispositivo_como_no_conectado() -> None:
    fixture = Fixture(devices=[_registered()])
    fixture.device.failure = DeviceError("la escritura no respondio")

    with pytest.raises(DeviceError):
        await fixture.service.connect(FIXED_ID)

    status = (await fixture.store.snapshot()).device
    assert status is not None and status.connected is False
    # Y el enlace queda CERRADO: dejarlo abierto permitia encender la tira por
    # `/lights/power` con la UI diciendo "desconectado", y abrir un segundo
    # dispositivo encima del ya enlazado.
    assert fixture.device.is_connected is False


@pytest.mark.asyncio
async def test_el_arranque_degradado_no_propaga_el_fallo_del_hardware() -> None:
    """ARCHITECTURE 7.5: adaptador no operativo -> el servicio arranca igual."""
    fixture = Fixture(device=UnreachableDevice(), devices=[_registered()])

    status = await fixture.service.try_connect(FIXED_ID)

    assert status.connected is False
    assert status.last_error == "device_write_failed"


@pytest.mark.asyncio
async def test_desconectar_publica_una_sola_vez_y_es_idempotente() -> None:
    fixture = Fixture(devices=[_registered()])
    await fixture.service.connect(FIXED_ID)
    version_conectado = (await fixture.store.snapshot()).version

    primero = await fixture.service.disconnect(FIXED_ID)
    segundo = await fixture.service.disconnect(FIXED_ID)

    assert primero.connected is False
    assert segundo == primero
    assert fixture.device.disconnect_calls == 2, "El adaptador debe poder cortar siempre"
    assert fixture.publisher.types.count(EventType.DEVICE_DISCONNECTED.value) == 1
    assert (await fixture.store.snapshot()).version == version_conectado + 1


@pytest.mark.asyncio
async def test_desconectar_algo_que_nunca_se_conecto_no_es_un_error() -> None:
    fixture = Fixture(devices=[_registered()])

    status = await fixture.service.disconnect(FIXED_ID)

    assert status == DeviceStatus(device_id=FIXED_ID, connected=False)
    assert (await fixture.store.snapshot()).version == 0
    assert fixture.publisher.events == []


@pytest.mark.asyncio
async def test_el_estado_de_un_dispositivo_que_no_ocupa_el_enlace_es_desconectado() -> None:
    other = _registered(id=uuid4(), name="Salon", address="AA:00")
    fixture = Fixture(devices=[_registered(), other])
    await fixture.service.connect(FIXED_ID)

    assert (await fixture.service.status(other.id)).connected is False
    assert (await fixture.service.status(FIXED_ID)).connected is True


@pytest.mark.asyncio
async def test_conectar_le_dice_al_adaptador_a_que_dispositivo_conectarse() -> None:
    """B3: `Device.address` se persistia, se indexaba y se devolvia... y no llegaba.

    La factoria construye UN adaptador desde la configuracion, asi que sin
    destino conectar la tira del salon y la del dormitorio ejecutaba el mismo
    codigo. Con un solo controlador es invisible; con dos, es el fallo entero.
    """
    salon = _registered(id=uuid4(), name="Salon", address="AA:00:00:00:00:01")
    dormitorio = _registered(id=uuid4(), name="Dormitorio", address="BB:00:00:00:00:02")
    fixture = Fixture(devices=[salon, dormitorio])

    await fixture.service.connect(salon.id)
    await fixture.service.disconnect(salon.id)
    await fixture.service.connect(dormitorio.id)

    assert fixture.device.targets == [
        DeviceTarget(address="AA:00:00:00:00:01"),
        DeviceTarget(address="BB:00:00:00:00:02"),
    ]


@pytest.mark.asyncio
async def test_un_dispositivo_sin_direccion_no_se_puede_conectar() -> None:
    """Una fila sin direccion nunca se emparejo con un controlador real.

    Se traduce a `DeviceError` (502) y no a un fallo interno: desde fuera el
    hecho es el mismo, y asi el arranque degradado del `lifespan` -- que absorbe
    `DeviceError` -- sigue arrancando en vez de tumbar el servicio.
    """
    fixture = Fixture(devices=[_registered(address=None)])

    with pytest.raises(DeviceError, match="direccion de transporte"):
        await fixture.service.connect(FIXED_ID)

    assert fixture.device.connect_calls == 0
