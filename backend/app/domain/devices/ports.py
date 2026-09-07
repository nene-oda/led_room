"""El puerto de dispositivo de luz: el unico contrato de control de hardware.

Este modulo NO importa nada de infraestructura ni ninguna biblioteca de
transporte. Es el seam que permite sustituir el hardware sin tocar escenas,
perfiles, efectos, la API ni el frontend (README 19 y 51).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from backend.app.domain.devices.models import (
    DeviceCapabilities,
    DeviceTarget,
    DiscoveredDevice,
)
from backend.app.domain.lighting import LightFrame


class DeviceError(Exception):
    """Error de dominio al operar un dispositivo de luz."""


class DeviceNotConnectedError(DeviceError):
    """Se intento una operacion sobre un dispositivo no conectado."""


class DeviceCapabilityError(DeviceError):
    """La operacion no esta soportada por las capacidades del dispositivo."""


class DeviceUnavailableError(DeviceError):
    """No hay transporte con el que operar: sin radio, apagada o sin permiso.

    Es distinto de `DeviceError` a proposito, y la diferencia la nota el
    usuario: "no encontre nada cerca" se arregla acercando la tira, mientras que
    "el Bluetooth de este equipo esta apagado" se arregla encendiendolo. Con un
    unico codigo, el cliente tenia que enumerar las dos posibilidades y no podia
    elegir ninguna.

    No describe un enlace caido ni una escritura fallida -- eso sigue siendo
    `DeviceError` --, sino la ausencia del medio: la respuesta correcta es 503,
    no 502.
    """


@runtime_checkable
class LightDevicePort(Protocol):
    """Contrato unico de control de luz.

    Las cinco operaciones del README 19 se conservan intactas. `apply_frame` se
    añade para que el motor de efectos aplique color y brillo en una sola
    llamada: a 20 fps, dos escrituras por fotograma serian 40 por segundo sobre
    el enlace BLE (ARCHITECTURE 4).
    """

    @property
    def capabilities(self) -> DeviceCapabilities:
        """Que sabe hacer este dispositivo."""
        ...

    @property
    def is_connected(self) -> bool: ...

    async def connect(self, target: DeviceTarget) -> None:
        """Abre el enlace con el dispositivo indicado.

        **El destino es un parametro y no configuracion del adaptador.** La
        factoria construye UN adaptador a partir de `Settings`, asi que sin este
        argumento `Device.address` -- que se persiste, se indexa con UNIQUE y se
        devuelve por la API -- no llegaba nunca aqui: conectar la tira del salon
        o la del dormitorio ejecutaba el mismo codigo. `DeviceTarget` es
        deliberadamente neutral (solo `address`), de modo que encaja igual con
        BLE (MAC o GUID de WinRT) que con un futuro adaptador de red (una IP).

        Debe ser **idempotente**: reconectar sobre un enlace ya abierto al mismo
        destino no puede duplicarlo.
        """
        ...

    async def disconnect(self) -> None: ...

    async def set_power(self, value: bool) -> None: ...

    async def set_color(self, red: int, green: int, blue: int) -> None:
        """Fija el color. Los tres canales van en 0-255."""
        ...

    async def set_brightness(self, brightness: int) -> None:
        """Fija el brillo como porcentaje 0-100 (ARCHITECTURE 3.3)."""
        ...

    async def apply_frame(self, frame: LightFrame) -> None:
        """Aplica color y brillo juntos.

        Un adaptador cuyo transporte no tenga un comando combinado puede
        resolverlo como la secuencia de las operaciones individuales; esa
        decision es invisible para quien llama.
        """
        ...


@runtime_checkable
class DeviceDiscoveryPort(Protocol):
    """Descubrimiento de dispositivos todavia no conectados (NEXT_STEPS A5).

    Es un puerto aparte, y no un metodo mas de `LightDevicePort`, porque aquel
    representa UN dispositivo ya identificado: escanear no presupone ninguno.
    Un adaptador BLE lo implementa envolviendo `BleakScanner`; uno de red, con
    mDNS o un barrido de la subred. La capa de aplicacion no nota la diferencia.
    """

    async def scan(self, timeout_s: float) -> Sequence[DiscoveredDevice]:
        """Devuelve lo visto durante `timeout_s` segundos.

        Nunca devuelve tipos del transporte (`BLEDevice` y similares): la
        traduccion a `DiscoveredDevice` es responsabilidad del adaptador.
        """
        ...
