from __future__ import annotations

import pytest

from backend.app.config import Settings
from backend.app.domain.devices.ports import LightDevicePort
from backend.app.domain.lighting import LightFrame, RGBColor
from backend.app.infrastructure.devices.factory import build_light_device
from backend.app.infrastructure.devices.null_adapter import NullLightDeviceAdapter


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


@pytest.mark.asyncio
async def test_el_estado_aplicado_es_inspeccionable() -> None:
    device = NullLightDeviceAdapter()

    await device.connect()
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


def test_la_factoria_devuelve_el_adaptador_sin_hardware_por_defecto(tmp_path: object) -> None:
    device = build_light_device(Settings())

    assert isinstance(device, NullLightDeviceAdapter)
    assert isinstance(device, LightDevicePort)


def test_el_adaptador_ble_falla_con_un_mensaje_explicito() -> None:
    """No se declara funcional hasta verificar el protocolo contra el hardware."""
    with pytest.raises(NotImplementedError, match="Fase 1"):
        build_light_device(Settings(device_adapter="lotus_lantern"))
