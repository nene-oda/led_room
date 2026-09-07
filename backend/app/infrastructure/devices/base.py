"""Base comun para los adaptadores de dispositivo de luz."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.domain.devices.models import DeviceCapabilities, DeviceTarget
from backend.app.domain.lighting import BRIGHTNESS_MAX, BRIGHTNESS_MIN, LightFrame


class BaseLightDevice(ABC):
    """Implementa lo que todo adaptador comparte.

    Aporta la validacion de rangos y una implementacion por defecto de
    `apply_frame` como `set_color` seguido de `set_brightness`. Un adaptador
    cuyo transporte tenga un comando combinado la sobreescribe y ahorra una
    escritura por fotograma.
    """

    def __init__(self, capabilities: DeviceCapabilities) -> None:
        self._capabilities = capabilities

    @property
    def capabilities(self) -> DeviceCapabilities:
        return self._capabilities

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    async def connect(self, target: DeviceTarget) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def set_power(self, value: bool) -> None: ...

    @abstractmethod
    async def set_color(self, red: int, green: int, blue: int) -> None: ...

    @abstractmethod
    async def set_brightness(self, brightness: int) -> None: ...

    async def apply_frame(self, frame: LightFrame) -> None:
        await self.set_color(frame.color.r, frame.color.g, frame.color.b)
        await self.set_brightness(frame.brightness)

    @staticmethod
    def _validate_color(red: int, green: int, blue: int) -> None:
        for name, value in (("red", red), ("green", green), ("blue", blue)):
            if not 0 <= value <= 255:
                raise ValueError(f"El canal {name} debe estar entre 0 y 255; se recibio {value}")

    @staticmethod
    def _validate_brightness(brightness: int) -> None:
        if not BRIGHTNESS_MIN <= brightness <= BRIGHTNESS_MAX:
            raise ValueError(
                f"El brillo debe ser un porcentaje entre {BRIGHTNESS_MIN} y {BRIGHTNESS_MAX}; "
                f"se recibio {brightness}"
            )
