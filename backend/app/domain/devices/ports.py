"""El puerto de dispositivo de luz: el unico contrato de control de hardware.

Este modulo NO importa nada de infraestructura ni ninguna biblioteca de
transporte. Es el seam que permite sustituir el hardware sin tocar escenas,
perfiles, efectos, la API ni el frontend (README 19 y 51).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.domain.devices.models import DeviceCapabilities
from backend.app.domain.lighting import LightFrame


class DeviceError(Exception):
    """Error de dominio al operar un dispositivo de luz."""


class DeviceNotConnectedError(DeviceError):
    """Se intento una operacion sobre un dispositivo no conectado."""


class DeviceCapabilityError(DeviceError):
    """La operacion no esta soportada por las capacidades del dispositivo."""


@runtime_checkable
class LightDevicePort(Protocol):
    """Contrato unico de control de luz.

    Las cinco operaciones del README 19 se conservan intactas. `apply_frame` se
    añade para que el motor de efectos aplique color y brillo en una sola
    llamada: a 20 fps, dos escrituras por fotograma serian 40 por segundo sobre
    el enlace BLE. Ver design.md D2.
    """

    @property
    def capabilities(self) -> DeviceCapabilities:
        """Que sabe hacer este dispositivo."""
        ...

    @property
    def is_connected(self) -> bool: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def set_power(self, value: bool) -> None: ...

    async def set_color(self, red: int, green: int, blue: int) -> None:
        """Fija el color. Los tres canales van en 0-255."""
        ...

    async def set_brightness(self, brightness: int) -> None:
        """Fija el brillo como porcentaje 0-100 (design.md D3)."""
        ...

    async def apply_frame(self, frame: LightFrame) -> None:
        """Aplica color y brillo juntos.

        Un adaptador cuyo transporte no tenga un comando combinado puede
        resolverlo como la secuencia de las operaciones individuales; esa
        decision es invisible para quien llama.
        """
        ...
