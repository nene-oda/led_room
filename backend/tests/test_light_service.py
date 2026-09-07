"""Casos de uso de la luz: orden de operaciones y guardia de capacidades."""

from __future__ import annotations

from uuid import UUID

import pytest

from backend.app.application.light_service import LightService
from backend.app.application.state_store import StateStore
from backend.app.domain.devices.models import (
    SINGLE_COLOR_STRIP,
    DeviceCapabilities,
    DeviceStatus,
    DeviceTarget,
)
from backend.app.domain.devices.ports import (
    DeviceCapabilityError,
    DeviceError,
    DeviceNotConnectedError,
)
from backend.app.domain.events import (
    LightBrightnessChanged,
    LightColorChanged,
    LightPowerChanged,
)
from backend.app.domain.lighting import RGBColor
from backend.tests.doubles import RecordingEventPublisher, RecordingLightDevice

PURPLE = RGBColor.from_hex("#7B00FF")
DEVICE_ID = UUID("11111111-2222-3333-4444-555555555555")
TARGET = DeviceTarget(address="BE:FF:00:11:22:33")

SIN_BRILLO = DeviceCapabilities(
    rgb=True,
    brightness=False,
    effects=False,
    addressable=False,
    segments=False,
    white_channel=False,
    music_mode=False,
)

SIN_RGB = SIN_BRILLO.model_copy(update={"rgb": False, "brightness": True})


async def _connected(
    capabilities: DeviceCapabilities = SINGLE_COLOR_STRIP,
) -> tuple[LightService, RecordingLightDevice, StateStore, RecordingEventPublisher]:
    """Enlace abierto: el adaptador conectado Y el store diciendolo.

    Las dos cosas, porque la fuente de verdad de "conectado" es el STORE
    (`LightService._require_connected`) y el adaptador es quien recibe las
    escrituras. Un doble en el que solo coincidiera una de las dos describiria
    justo el estado divergente que se acaba de corregir.
    """
    device = RecordingLightDevice(capabilities=capabilities)
    await device.connect(TARGET)
    publisher = RecordingEventPublisher()
    store = StateStore(publisher)
    async with store.mutate() as draft:
        draft.set_device(DeviceStatus(device_id=DEVICE_ID, connected=True))
    return LightService(device, store), device, store, publisher


@pytest.mark.asyncio
async def test_encender_escribe_actualiza_el_estado_y_publica() -> None:
    service, device, store, publisher = await _connected()

    light = await service.set_power(True)

    assert device.operations == ["set_power:True"]
    assert light.power is True
    assert (await store.snapshot()).version == 2, "1 = alta del enlace, 2 = el encendido"
    assert publisher.events == [LightPowerChanged(power=True)]


@pytest.mark.asyncio
async def test_el_color_viaja_como_rgb_en_el_evento_y_en_mayusculas_en_el_estado() -> None:
    """La forma del cable es del transporte; el dominio publica `RGBColor`."""
    service, device, store, publisher = await _connected()

    light = await service.set_color(PURPLE)

    assert device.operations == ["set_color:123,0,255"]
    assert light.color == PURPLE
    assert light.color.to_hex() == "#7B00FF"
    assert publisher.events == [LightColorChanged(color=PURPLE)]
    assert (await store.snapshot()).light.color == PURPLE


@pytest.mark.asyncio
async def test_el_brillo_se_escribe_y_se_publica_como_porcentaje() -> None:
    service, device, _, publisher = await _connected()

    light = await service.set_brightness(20)

    assert device.operations == ["set_brightness:20"]
    assert light.brightness == 20
    assert publisher.events == [LightBrightnessChanged(brightness=20)]


@pytest.mark.asyncio
async def test_cada_comando_conserva_los_otros_campos_del_estado() -> None:
    service, _, store, _ = await _connected()

    await service.set_power(True)
    await service.set_color(PURPLE)
    await service.set_brightness(30)

    state = await store.snapshot()
    assert state.light.power is True
    assert state.light.color == PURPLE
    assert state.light.brightness == 30
    assert state.version == 4, "1 = alta del enlace + 3 comandos"


@pytest.mark.asyncio
async def test_operar_sin_dispositivo_conectado_lanza_y_no_escribe_nada() -> None:
    device = RecordingLightDevice()
    service = LightService(device, StateStore(RecordingEventPublisher()))

    with pytest.raises(DeviceNotConnectedError):
        await service.set_power(True)

    assert device.writes == []


@pytest.mark.asyncio
async def test_manda_el_store_aunque_el_adaptador_diga_que_esta_conectado() -> None:
    """B4: la fuente de verdad de "conectado" es UNA, y es el store.

    Un `_reconcile` fallido dejaba el enlace abierto con el estado diciendo
    `connected: false`. Preguntandole al adaptador, `POST /lights/power`
    respondia 200 y encendia la tira mientras la UI decia "desconectado".
    """
    device = RecordingLightDevice()
    await device.connect(TARGET)
    service = LightService(device, StateStore(RecordingEventPublisher()))

    with pytest.raises(DeviceNotConnectedError):
        await service.set_power(True)

    assert device.is_connected, "El doble sigue enlazado: la divergencia es el supuesto del test"
    assert device.writes == []


@pytest.mark.asyncio
async def test_sin_capacidad_de_brillo_se_rechaza_y_el_adaptador_no_recibe_nada() -> None:
    """Criterio de aceptacion de NEXT_STEPS A2.

    `DeviceCapabilityError` estaba definido y no se lanzaba en ningun sitio: un
    puerto con capacidades que nadie consulta es documentacion, no un seam.
    """
    service, device, store, publisher = await _connected(SIN_BRILLO)

    with pytest.raises(DeviceCapabilityError, match="brightness"):
        await service.set_brightness(60)

    assert device.writes == []
    assert (await store.snapshot()).version == 1, "Solo el alta del enlace"
    assert publisher.events == []


@pytest.mark.asyncio
async def test_sin_capacidad_rgb_se_rechaza_el_color() -> None:
    service, device, _, _ = await _connected(SIN_RGB)

    with pytest.raises(DeviceCapabilityError, match="rgb"):
        await service.set_color(PURPLE)

    assert device.writes == []


@pytest.mark.asyncio
async def test_un_brillo_fuera_de_rango_se_rechaza_antes_de_escribir() -> None:
    """El rango 0-100 es `Percent`, la unica definicion del dominio: 422, no 502."""
    service, device, _, publisher = await _connected()

    with pytest.raises(ValueError, match=r"less_than_equal"):
        await service.set_brightness(101)

    assert device.writes == []
    assert publisher.events == []


@pytest.mark.asyncio
async def test_si_el_dispositivo_rechaza_la_escritura_no_hay_estado_nuevo_ni_evento() -> None:
    """Solo se publica lo que el dispositivo acepto (NEXT_STEPS A4)."""
    service, device, store, publisher = await _connected()
    device.failure = DeviceError("el enlace BLE se cayo")

    with pytest.raises(DeviceError):
        await service.set_color(PURPLE)

    assert device.operations == ["set_color:123,0,255"], "Se intento escribir, y fallo"
    state = await store.snapshot()
    assert state.version == 1, "Solo el alta del enlace: el comando no confirmo nada"
    assert state.light.color != PURPLE
    assert publisher.events == []
