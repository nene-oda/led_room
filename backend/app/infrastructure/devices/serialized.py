"""Escritor unico por dispositivo: una sola escritura en vuelo.

Esto es **correccion de concurrencia**, no *throttling*. Son dos cosas
distintas y viven en archivos distintos a proposito (ARCHITECTURE 4,
NEXT_STEPS A2):

* Aqui: dos peticiones simultaneas no pueden intercalar sus escrituras sobre el
  mismo enlace. Es una invariante del transporte y se cumple siempre.
* En `application/`: cuantas actualizaciones por segundo se le permiten al
  usuario. Es politica de producto, configurable, y descarta valores viejos.

Mezclarlas produciria un limitador que tambien serializa y un serializador que
tambien descarta comandos: nadie sabria cual de los dos se comio una escritura.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from backend.app.domain.devices.models import DeviceCapabilities, DeviceTarget
from backend.app.domain.devices.ports import DeviceError, LightDevicePort
from backend.app.domain.lighting import LightFrame


class SerializedLightDevice:
    """Envuelve cualquier `LightDevicePort` y cumple el mismo contrato.

    Se compone en la factoria, de modo que todo adaptador presente y futuro lo
    hereda gratis: ningun adaptador debe volver a escribir su propio `Lock`.
    """

    def __init__(
        self,
        device: LightDevicePort,
        *,
        write_timeout_s: float,
        min_write_interval_s: float = 0.0,
    ) -> None:
        """Compone el serializador.

        `min_write_interval_s` es el retardo minimo entre tramas. Vale 0 por
        defecto porque **todavia no se conoce**: el valor real se mide con el
        hardware delante (Fase 0, "retardo minimo entre escrituras sin perder
        tramas"). Poner una cifra inventada aqui seria fijar un limite de
        rendimiento sin evidencia.
        """
        if write_timeout_s <= 0:
            raise ValueError(
                f"El timeout de escritura debe ser positivo; se recibio {write_timeout_s}"
            )
        if min_write_interval_s < 0:
            raise ValueError(
                "El retardo minimo entre tramas no puede ser negativo; "
                f"se recibio {min_write_interval_s}"
            )

        self._device = device
        self._write_timeout_s = write_timeout_s
        self._min_write_interval_s = min_write_interval_s
        self._lock = asyncio.Lock()
        self._last_write_end: float | None = None

    @property
    def capabilities(self) -> DeviceCapabilities:
        return self._device.capabilities

    @property
    def is_connected(self) -> bool:
        return self._device.is_connected

    async def connect(self, target: DeviceTarget) -> None:
        """Delega sin tomar el cerrojo de escritura.

        El ciclo de vida del enlace es responsabilidad del adaptador envuelto,
        que es quien tiene la maquina de estados y su propio timeout de
        conexion. Bloquear aqui solo añadiria un segundo sitio donde razonar
        sobre lo mismo, y una conexion lenta congelaria las escrituras sin
        aportar ninguna garantia extra.
        """
        await self._device.connect(target)

    async def disconnect(self) -> None:
        """Delega sin tomar el cerrojo: debe poder cortar, no esperar turno."""
        await self._device.disconnect()

    async def set_power(self, value: bool) -> None:
        await self._write("set_power", lambda: self._device.set_power(value))

    async def set_color(self, red: int, green: int, blue: int) -> None:
        await self._write("set_color", lambda: self._device.set_color(red, green, blue))

    async def set_brightness(self, brightness: int) -> None:
        await self._write("set_brightness", lambda: self._device.set_brightness(brightness))

    async def apply_frame(self, frame: LightFrame) -> None:
        """Un solo turno para el fotograma completo.

        Delega en el `apply_frame` del adaptador en vez de llamar a
        `self.set_color` y `self.set_brightness`: eso serian dos turnos, con lo
        que otra escritura podria colarse entre el color y el brillo del mismo
        fotograma (y, con un cerrojo no reentrante, se bloquearia a si mismo).
        """
        await self._write("apply_frame", lambda: self._device.apply_frame(frame))

    async def _write(self, operation: str, call: Callable[[], Awaitable[None]]) -> None:
        """Ejecuta una escritura en exclusiva, con retardo minimo y timeout.

        La corrutina se crea DENTRO del cerrojo (por eso el parametro es una
        funcion y no un awaitable ya construido): si la tarea muriera esperando
        turno, un awaitable creado antes quedaria sin consumir y Python emitiria
        un aviso de corrutina nunca esperada.
        """
        async with self._lock:
            await self._wait_min_interval()
            try:
                await asyncio.wait_for(call(), self._write_timeout_s)
            except TimeoutError as error:
                # Un write colgado retiene el cerrojo indefinidamente y congela
                # la aplicacion entera. `wait_for` cancela la operacion y el
                # `async with` libera el cerrojo tambien por esta rama.
                raise DeviceError(
                    f"La escritura {operation} no respondio en {self._write_timeout_s:g} s"
                ) from error
            finally:
                self._last_write_end = time.monotonic()

    async def _wait_min_interval(self) -> None:
        """Duerme DENTRO del cerrojo.

        Fuera, dos llamadas concurrentes dormirian a la vez y entrarian juntas:
        el retardo no separaria nada.
        """
        if self._min_write_interval_s <= 0 or self._last_write_end is None:
            return

        remaining = self._min_write_interval_s - (time.monotonic() - self._last_write_end)
        if remaining > 0:
            await asyncio.sleep(remaining)
