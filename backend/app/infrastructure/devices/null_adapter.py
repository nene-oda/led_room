"""Adaptador de luz que no toca hardware.

Permite que el servicio arranque y sea verificable en cualquier host, tenga o no
radio Bluetooth: en Windows con Docker Desktop, en CI, y en los tests.
"""

from __future__ import annotations

import logging

from backend.app.domain.devices.models import (
    SINGLE_COLOR_STRIP,
    DeviceCapabilities,
    DeviceTarget,
)
from backend.app.domain.lighting import RGBColor
from backend.app.infrastructure.devices.base import BaseLightDevice

logger = logging.getLogger(__name__)


class NullLightDeviceAdapter(BaseLightDevice):
    """Adaptador en memoria: registra el estado aplicado y lo deja inspeccionable."""

    def __init__(self, capabilities: DeviceCapabilities | None = None) -> None:
        super().__init__(capabilities or SINGLE_COLOR_STRIP)
        self._connected = False
        self._target: DeviceTarget | None = None
        self._power = False
        self._color = RGBColor(r=0, g=0, b=0)
        self._brightness = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def target(self) -> DeviceTarget | None:
        """Ultimo destino con el que se abrio el enlace. Inspeccionable en los tests."""
        return self._target

    @property
    def power(self) -> bool:
        return self._power

    @property
    def color(self) -> RGBColor:
        return self._color

    @property
    def brightness(self) -> int:
        return self._brightness

    async def connect(self, target: DeviceTarget) -> None:
        self._connected = True
        self._target = target
        logger.info(
            "Dispositivo sin hardware conectado a %s (no se toca ninguna radio)",
            target.address,
        )

    async def disconnect(self) -> None:
        self._connected = False
        self._target = None
        logger.info("Dispositivo sin hardware desconectado")

    async def set_power(self, value: bool) -> None:
        self._power = value
        logger.debug("power=%s", value)

    async def set_color(self, red: int, green: int, blue: int) -> None:
        self._validate_color(red, green, blue)
        self._color = RGBColor(r=red, g=green, b=blue)
        logger.debug("color=%s", self._color.to_hex())

    async def set_brightness(self, brightness: int) -> None:
        self._validate_brightness(brightness)
        self._brightness = brightness
        logger.debug("brightness=%s%%", brightness)
