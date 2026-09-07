"""El adaptador de control BLE, probado sin ninguna radio.

El cliente se inyecta, asi que estas pruebas corren en cualquier host y en la
CI. Lo que NO comprueban -- porque no puede comprobarlo ningun test -- es que la
tira obedezca: `fff3` escribe sin respuesta y el controlador no acusa nada. Esa
verificacion es manual y esta en `docs/BLE_PROTOCOL.md` seccion 3.
"""

from __future__ import annotations

import pytest
from bleak.exc import (
    BleakBluetoothNotAvailableError,
    BleakBluetoothNotAvailableReason,
    BleakDeviceNotFoundError,
    BleakError,
)

from backend.app.domain.devices.models import DeviceTarget
from backend.app.domain.devices.ports import (
    DeviceError,
    DeviceNotConnectedError,
    DeviceUnavailableError,
    LightDevicePort,
)
from backend.app.domain.lighting import LightFrame, RGBColor
from backend.app.infrastructure.bluetooth import protocol
from backend.app.infrastructure.bluetooth.lotus_lantern import (
    BleClient,
    LotusLanternBLEAdapter,
)

TIRA = DeviceTarget(address="AA:BB:CC:DD:EE:FF")
OTRA = DeviceTarget(address="11:22:33:44:55:66")


class ClienteFalso:
    """Cliente BLE de mentira: apunta lo escrito y no toca nada."""

    def __init__(self, address: str, *, fallo: Exception | None = None) -> None:
        self.address = address
        self.escrituras: list[tuple[str, bytes, bool | None]] = []
        self.conexiones = 0
        self.desconexiones = 0
        self._conectado = False
        self._fallo = fallo

    @property
    def is_connected(self) -> bool:
        return self._conectado

    async def connect(self, **kwargs: object) -> None:
        if self._fallo is not None:
            raise self._fallo
        self.conexiones += 1
        self._conectado = True

    async def disconnect(self) -> None:
        self.desconexiones += 1
        self._conectado = False

    async def write_gatt_char(
        self, char_specifier: str, data: bytes, response: bool | None = None
    ) -> None:
        if self._fallo is not None:
            raise self._fallo
        self.escrituras.append((char_specifier, data, response))


class Fabrica:
    """Entrega clientes falsos y conserva el ultimo, para poder inspeccionarlo."""

    def __init__(self, fallo: Exception | None = None) -> None:
        self.creados: list[ClienteFalso] = []
        self._fallo = fallo

    def __call__(self, address: str, timeout_s: float) -> BleClient:
        cliente = ClienteFalso(address, fallo=self._fallo)
        self.creados.append(cliente)
        self.timeout_s = timeout_s
        return cliente

    @property
    def ultimo(self) -> ClienteFalso:
        return self.creados[-1]


def _adaptador(fabrica: Fabrica, *, connect_timeout_s: float = 20.0) -> LotusLanternBLEAdapter:
    return LotusLanternBLEAdapter(connect_timeout_s=connect_timeout_s, client_factory=fabrica)


def test_cumple_el_puerto_de_dispositivo_de_luz() -> None:
    """Es lo unico que la aplicacion conoce: si no lo cumple, no es sustituible."""
    assert isinstance(_adaptador(Fabrica()), LightDevicePort)


@pytest.mark.asyncio
async def test_el_color_llega_al_hardware_como_la_trama_verificada() -> None:
    fabrica = Fabrica()
    adaptador = _adaptador(fabrica)
    await adaptador.connect(TIRA)

    await adaptador.set_color(255, 0, 0)

    uuid, trama, response = fabrica.ultimo.escrituras[-1]
    assert trama == protocol.encode_color(255, 0, 0)
    assert uuid == protocol.WRITE_CHARACTERISTIC_UUID
    # `fff3` NO admite escritura con respuesta: pedirla falla.
    assert response is False


@pytest.mark.asyncio
async def test_el_brillo_y_el_encendido_usan_sus_tramas() -> None:
    fabrica = Fabrica()
    adaptador = _adaptador(fabrica)
    await adaptador.connect(TIRA)

    await adaptador.set_brightness(40)
    await adaptador.set_power(False)

    enviadas = [trama for _, trama, _ in fabrica.ultimo.escrituras]
    assert enviadas == [protocol.encode_brightness(40), protocol.encode_power(False)]


@pytest.mark.asyncio
async def test_aplicar_un_fotograma_manda_color_y_brillo() -> None:
    """El controlador no tiene comando combinado: son dos escrituras."""
    fabrica = Fabrica()
    adaptador = _adaptador(fabrica)
    await adaptador.connect(TIRA)

    await adaptador.apply_frame(
        LightFrame(color=RGBColor(r=0, g=255, b=0), brightness=70, duration_ms=50)
    )

    enviadas = [trama for _, trama, _ in fabrica.ultimo.escrituras]
    assert enviadas == [protocol.encode_color(0, 255, 0), protocol.encode_brightness(70)]


@pytest.mark.asyncio
async def test_escribir_sin_enlace_no_es_un_fallo_de_transporte() -> None:
    """Distingue "no conectaste" de "el enlace se cayo": son 409 y 502."""
    with pytest.raises(DeviceNotConnectedError):
        await _adaptador(Fabrica()).set_color(1, 2, 3)


@pytest.mark.asyncio
async def test_reconectar_al_mismo_destino_no_reabre_el_enlace() -> None:
    """El controlador admite UNA conexion: un segundo enlace echaria al primero."""
    fabrica = Fabrica()
    adaptador = _adaptador(fabrica)

    await adaptador.connect(TIRA)
    await adaptador.connect(TIRA)

    assert len(fabrica.creados) == 1
    assert fabrica.ultimo.conexiones == 1


@pytest.mark.asyncio
async def test_conectar_a_otro_destino_cierra_el_anterior() -> None:
    """Un adaptador gobierna un dispositivo a la vez."""
    fabrica = Fabrica()
    adaptador = _adaptador(fabrica)

    await adaptador.connect(TIRA)
    primero = fabrica.ultimo
    await adaptador.connect(OTRA)

    assert primero.desconexiones == 1
    assert adaptador.address == OTRA.address


@pytest.mark.asyncio
async def test_desconectar_es_idempotente_y_seguro_sin_enlace() -> None:
    adaptador = _adaptador(Fabrica())

    await adaptador.disconnect()
    await adaptador.disconnect()

    assert not adaptador.is_connected


@pytest.mark.asyncio
async def test_un_fallo_al_cerrar_no_deja_el_adaptador_bloqueado() -> None:
    """Si el estado local no se limpiara, no se podria volver a conectar nunca.

    `connect()` es idempotente sobre el mismo destino: creerse conectado a algo
    que ya no responde seria una trampa sin salida.
    """
    fabrica = Fabrica()
    adaptador = _adaptador(fabrica)
    await adaptador.connect(TIRA)
    cliente = fabrica.ultimo

    async def falla_al_cerrar() -> None:
        raise BleakError("el enlace ya no existe")

    cliente.disconnect = falla_al_cerrar  # type: ignore[method-assign]
    await adaptador.disconnect()

    assert not adaptador.is_connected
    await adaptador.connect(TIRA)
    assert adaptador.is_connected


@pytest.mark.asyncio
async def test_sin_radio_es_indisponibilidad_no_un_fallo_del_dispositivo() -> None:
    """503, no 502: se arregla encendiendo el Bluetooth, no acercando la tira."""
    fallo = BleakBluetoothNotAvailableError(
        "D-Bus /org/bluez/hci0 dijo que no", BleakBluetoothNotAvailableReason.POWERED_OFF
    )

    with pytest.raises(DeviceUnavailableError):
        await _adaptador(Fabrica(fallo)).connect(TIRA)


@pytest.mark.asyncio
async def test_sin_socket_de_dbus_tambien_es_indisponibilidad() -> None:
    """El caso del contenedor: `dbus_fast` sube un `FileNotFoundError` crudo."""
    fallo = FileNotFoundError(2, "No such file", "/run/dbus/system_bus_socket")

    with pytest.raises(DeviceUnavailableError) as raised:
        await _adaptador(Fabrica(fallo)).connect(TIRA)

    assert "system_bus_socket" not in str(raised.value)


@pytest.mark.asyncio
async def test_no_encontrar_la_tira_explica_que_puede_estar_ocupada() -> None:
    """Es la causa mas frecuente: la app del movil la tiene tomada."""
    fallo = BleakDeviceNotFoundError("no esta")

    with pytest.raises(DeviceError) as raised:
        await _adaptador(Fabrica(fallo)).connect(TIRA)

    assert not isinstance(raised.value, DeviceUnavailableError)
    assert "conectado" in str(raised.value)


@pytest.mark.asyncio
async def test_un_error_de_bleak_no_se_filtra_al_cliente() -> None:
    """El `str()` de Bleak puede llevar rutas de D-Bus o la direccion real."""
    fallo = BleakError("dbus error org.bluez /org/bluez/hci0/dev_AA_BB")

    with pytest.raises(DeviceError) as raised:
        await _adaptador(Fabrica(fallo)).connect(TIRA)

    assert "bluez" not in str(raised.value)


@pytest.mark.asyncio
async def test_un_color_invalido_no_llega_al_enlace() -> None:
    """Se corta antes de escribir: el rango es del dominio, no del transporte."""
    fabrica = Fabrica()
    adaptador = _adaptador(fabrica)
    await adaptador.connect(TIRA)

    with pytest.raises(ValueError, match="entre 0 y 255"):
        await adaptador.set_color(256, 0, 0)

    assert fabrica.ultimo.escrituras == []


def test_las_capacidades_no_prometen_lo_que_el_hardware_no_hace() -> None:
    """Una tira de un solo color no es direccionable: decirlo rompe los efectos."""
    capacidades = _adaptador(Fabrica()).capabilities

    assert capacidades.rgb
    assert capacidades.brightness
    assert not capacidades.addressable
    assert not capacidades.segments
