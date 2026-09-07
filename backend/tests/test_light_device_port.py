from __future__ import annotations

import pytest

from backend.app.config import Settings
from backend.app.domain.devices.models import DeviceTarget, DeviceType
from backend.app.domain.devices.ports import LightDevicePort
from backend.app.domain.lighting import LightFrame, RGBColor
from backend.app.infrastructure.devices.factory import build_light_device
from backend.app.infrastructure.devices.null_adapter import NullLightDeviceAdapter
from backend.app.infrastructure.devices.serialized import SerializedLightDevice


def test_el_adaptador_sin_hardware_cumple_el_puerto() -> None:
    """Rompe la build el dia que una firma del adaptador deje de encajar."""
    assert isinstance(NullLightDeviceAdapter(), LightDevicePort)


def test_capacidades_del_hardware_actual() -> None:
    capabilities = NullLightDeviceAdapter().capabilities

    assert capabilities.rgb
    assert capabilities.brightness
    assert not capabilities.addressable
    assert not capabilities.segments
    assert not capabilities.white_channel
    # Que el controlador tenga microfono no prueba que el protocolo BLE permita
    # activarlo: eso lo decide la Fase 0 (ARCHITECTURE 5.4).
    assert not capabilities.music_mode


@pytest.mark.asyncio
async def test_el_estado_aplicado_es_inspeccionable() -> None:
    device = NullLightDeviceAdapter()

    await device.connect(DeviceTarget(address="BE:FF:00:11:22:33"))
    await device.set_power(True)
    await device.set_color(123, 0, 255)
    await device.set_brightness(65)

    assert device.is_connected
    assert device.power
    assert device.color == RGBColor(r=123, g=0, b=255)
    assert device.brightness == 65


@pytest.mark.asyncio
async def test_apply_frame_aplica_color_y_brillo() -> None:
    device = NullLightDeviceAdapter()
    frame = LightFrame(color=RGBColor.from_hex("#7B00FF"), brightness=60, duration_ms=50)

    await device.apply_frame(frame)

    assert device.color.to_hex() == "#7B00FF"
    assert device.brightness == 60


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("red", "green", "blue"),
    [(256, 0, 0), (-1, 0, 0), (0, 300, 0), (0, 0, -5)],
)
async def test_color_fuera_de_rango_se_rechaza(red: int, green: int, blue: int) -> None:
    device = NullLightDeviceAdapter()
    previous = device.color

    with pytest.raises(ValueError):
        await device.set_color(red, green, blue)

    assert device.color == previous


@pytest.mark.asyncio
@pytest.mark.parametrize("brightness", [-1, 101, 255])
async def test_brillo_fuera_de_rango_se_rechaza(brightness: int) -> None:
    device = NullLightDeviceAdapter()

    with pytest.raises(ValueError):
        await device.set_brightness(brightness)

    assert device.brightness == 0


def test_la_factoria_devuelve_un_dispositivo_serializado_por_defecto() -> None:
    """La factoria compone el escritor unico sobre el adaptador elegido.

    Ya no devuelve el `NullLightDeviceAdapter` pelado: la serializacion de las
    escrituras se compone en un solo sitio para que ningun adaptador tenga que
    acordarse de ella (NEXT_STEPS A2). Que `null` sea el adaptador por defecto
    se comprueba en `test_device_registry.py`, contra la tabla que lo decide.
    """
    device = build_light_device(Settings())

    assert isinstance(device, SerializedLightDevice)
    assert isinstance(device, LightDevicePort)


def test_el_adaptador_ble_se_construye_ya_serializado() -> None:
    """La serializacion se compone en la factoria, no en el adaptador.

    Es lo que garantiza que ningun adaptador -- este ni los futuros -- tenga que
    acordarse de traer su propio `Lock`. Si algun dia la factoria dejara de
    envolver, dos peticiones simultaneas intercalarian escrituras sobre el mismo
    enlace BLE y nadie lo notaria hasta tener la tira delante.
    """
    device = build_light_device(Settings(device_adapter=DeviceType.LOTUS_LANTERN))

    assert isinstance(device, SerializedLightDevice)
    assert isinstance(device, LightDevicePort)


@pytest.mark.asyncio
async def test_conectar_lleva_el_destino_al_adaptador() -> None:
    """B3: `Device.address` se persiste e indexa, pero antes no llegaba aqui.

    Sin destino, conectar la tira del salon y la del dormitorio ejecutaba
    exactamente el mismo codigo y los tests seguian en verde mintiendo.
    """
    device = NullLightDeviceAdapter()
    salon = DeviceTarget(address="AA:00:00:00:00:01")

    await device.connect(salon)
    assert device.target == salon

    await device.disconnect()
    assert device.target is None


def test_el_destino_no_puede_ser_una_direccion_vacia() -> None:
    with pytest.raises(ValueError):
        DeviceTarget(address="")
