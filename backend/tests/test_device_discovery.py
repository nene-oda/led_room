"""El puerto de descubrimiento y su implementacion sin radio (NEXT_STEPS A5)."""

from __future__ import annotations

import time

import pytest

from backend.app.config import Settings
from backend.app.domain.devices.models import DeviceType, DiscoveredDevice
from backend.app.domain.devices.ports import DeviceDiscoveryPort
from backend.app.infrastructure.devices.factory import build_device_discovery
from backend.app.infrastructure.devices.null_discovery import NullDiscoveryAdapter


def test_el_descubrimiento_sin_radio_cumple_el_puerto() -> None:
    assert isinstance(NullDiscoveryAdapter(), DeviceDiscoveryPort)


@pytest.mark.asyncio
async def test_sin_radio_no_se_descubre_nada() -> None:
    """Devolver una lista vacia es lo honesto; inventar dispositivos, no."""
    assert await NullDiscoveryAdapter().scan(timeout_s=10.0) == ()


@pytest.mark.asyncio
async def test_devuelve_la_lista_fija_que_se_le_configura() -> None:
    seen = DiscoveredDevice(name="ELK-BLEDOM", address="AA:BB:CC:DD:EE:FF", rssi=-63)

    result = await NullDiscoveryAdapter([seen]).scan(timeout_s=1.0)

    assert list(result) == [seen]


@pytest.mark.asyncio
async def test_el_escaneo_sin_radio_no_gasta_el_timeout() -> None:
    """Dormir el timeout haria que cada arranque de CI pagara diez segundos."""
    started = time.perf_counter()

    await NullDiscoveryAdapter().scan(timeout_s=3600.0)

    assert time.perf_counter() - started < 0.5


def test_la_factoria_elige_el_descubrimiento_segun_la_configuracion() -> None:
    discovery = build_device_discovery(Settings(device_adapter=DeviceType.NULL))

    assert isinstance(discovery, NullDiscoveryAdapter)
    assert isinstance(discovery, DeviceDiscoveryPort)
