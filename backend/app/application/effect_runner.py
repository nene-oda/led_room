"""El bucle de reproduccion: **un unico efecto activo por dispositivo**.

Hay una conexion BLE y un solo worker de uvicorn, asi que dos bucles a la vez
intercalarian fotogramas de efectos distintos sobre la misma tira. Todo lo que
aqui se decide es orquestacion temporal; la matematica vive en `domain/effects`
y la escritura, detras de `LightDevicePort`.

Reglas que sostienen el diseño (NEXT_STEPS 6.4 y 6.5):

* `play()` cancela la tarea anterior **y la espera**. Descartarla sin esperarla
  es exactamente como se acumulan tareas que siguen escribiendo por BLE.
* El cuerpo **nunca traga `CancelledError`**: lo relanza. Quien cancelo es quien
  decide que significa.
* El `finally` **no apaga la luz**: el ultimo fotograma se queda puesto. Apagar
  produciria un parpadeo negro entre dos escenas encadenadas.
* **Una escritura por fotograma** (`apply_frame`), sin cola: profundidad 1.
* Si el adaptador tarda mas que el periodo, se **descarta** con una linea de
  tiempo monotona. Acumular añade latencia sin cota: a los 30 s el usuario veria
  lo que pidio hace 10.
* El **ultimo** fotograma nunca se descarta: es el destino del efecto y es lo
  que se queda encendido.
* Una desconexion a mitad **para**, no reintenta. Un enlace a medias con
  reintentos en bucle apretado genera cola y empeora la reconexion.

Este modulo no conoce el estado global ni el WebSocket: informa del final por un
callback y es la capa de aplicacion (`effect_service`) la que publica los
eventos. El motor no debe saber que existe un socket.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from uuid import UUID

from backend.app.application.clock import Clock
from backend.app.domain.devices.ports import (
    DeviceError,
    DeviceNotConnectedError,
    LightDevicePort,
)
from backend.app.domain.effects.adaptation import adapt_frame
from backend.app.domain.effects.engine import EffectPlan, segment_stream
from backend.app.domain.effects.frames import render_segments

logger = logging.getLogger(__name__)

_MS_PER_SECOND = 1000.0


class StopReason(StrEnum):
    """Por que dejo de sonar un efecto. Solo para el log y el llamante.

    La cancelacion no esta aqui a proposito: quien cancela ya sabe por que lo
    hizo y no necesita que se lo cuenten de vuelta.
    """

    COMPLETED = "completed"
    DEVICE_ERROR = "device_error"
    DISCONNECTED = "disconnected"


#: Se invoca **solo** cuando el efecto termina solo: nunca tras una cancelacion.
FinishedCallback = Callable[[UUID, StopReason], Awaitable[None]]


class EffectRunner:
    """Titular de la unica tarea de reproduccion del proceso."""

    def __init__(self, device: LightDevicePort, clock: Clock) -> None:
        self._device = device
        self._clock = clock
        self._task: asyncio.Task[None] | None = None
        self._dropped = 0

    @property
    def is_running(self) -> bool:
        return self._task is not None

    @property
    def dropped_frames(self) -> int:
        """Fotogramas descartados en la ultima reproduccion. Diagnostico."""
        return self._dropped

    async def play(self, plan: EffectPlan, *, on_finished: FinishedCallback | None = None) -> None:
        """Sustituye lo que estuviera sonando. Nunca deja dos bucles vivos.

        El callback se pasa **por reproduccion** y no al construir el runner:
        describe el final de *este* plan, y recibirlo aqui evita que el runner y
        quien lo escucha tengan que conocerse en el constructor.
        """
        await self.stop()
        self._task = asyncio.create_task(
            self._run(plan, on_finished), name=f"effect:{plan.effect_id}"
        )

    async def stop(self) -> None:
        """Cancela y **espera**. Idempotente.

        Esperar es la parte que importa: sin ella, la tarea vieja seguiria
        escribiendo por BLE mientras la nueva empieza, y los fotogramas de dos
        efectos se intercalarian sobre la misma tira.
        """
        task, self._task = self._task, None
        if task is None:
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            # Cancelacion pedida por nosotros: se absorbe. Si el cancelado fue
            # el llamante, la tarea aun no habra terminado y hay que relanzar,
            # o una parada perderia la cancelacion de quien la pidio.
            if not task.cancelled():
                raise

    async def _run(self, plan: EffectPlan, on_finished: FinishedCallback | None) -> None:
        """Cuerpo de la tarea. Traduce el final en un motivo, sin apagar la luz."""
        self._dropped = 0
        reason = StopReason.COMPLETED
        try:
            await self._render(plan)
        except asyncio.CancelledError:
            logger.debug("Efecto %s cancelado", plan.effect_id)
            raise
        except DeviceNotConnectedError as error:
            reason = StopReason.DISCONNECTED
            logger.warning("Efecto %s detenido: enlace caido (%s)", plan.effect_id, error)
        except DeviceError as error:
            reason = StopReason.DEVICE_ERROR
            logger.warning("Efecto %s detenido: fallo de escritura (%s)", plan.effect_id, error)
        finally:
            # Agregado, jamas una linea por fotograma: a 20 fps un log por
            # descarte convierte el diagnostico en el cuello de botella.
            if self._dropped:
                logger.warning(
                    "Efecto %s: %d fotogramas descartados por un adaptador mas lento que %d ms",
                    plan.effect_id,
                    self._dropped,
                    plan.frame_duration_ms,
                )

        # Fuera del `try`: solo se llega aqui si el efecto acabo por si mismo.
        current = asyncio.current_task()
        if self._task is current:
            self._task = None
        await self._notify(on_finished, plan.effect_id, reason)

    async def _render(self, plan: EffectPlan) -> None:
        """Aplica los fotogramas siguiendo una linea de tiempo monotona.

        El plazo del fotograma `n` es `t0 + suma(duraciones anteriores)`. Si ya
        paso, se **avanza el indice** en vez de dormir un intervalo negativo: es
        la diferencia entre un efecto que se retrasa y uno que acumula.
        """
        capabilities = self._device.capabilities
        frames = render_segments(segment_stream(plan), fps=plan.fps, color_space=plan.color_space)

        started = self._clock.monotonic()
        deadline_ms = 0.0
        pending = next(frames, None)

        while pending is not None:
            # Una posicion de adelanto: es lo unico que hace falta para saber si
            # este fotograma es el ultimo, y el ultimo nunca se descarta.
            upcoming = next(frames, None)
            elapsed_ms = (self._clock.monotonic() - started) * _MS_PER_SECOND

            if upcoming is not None and deadline_ms < elapsed_ms:
                self._dropped += 1
            else:
                remaining_s = (deadline_ms - elapsed_ms) / _MS_PER_SECOND
                if remaining_s > 0:
                    await self._clock.sleep(remaining_s)
                await self._device.apply_frame(adapt_frame(pending, capabilities))

            deadline_ms += pending.duration_ms
            pending = upcoming

    async def _notify(
        self,
        on_finished: FinishedCallback | None,
        effect_id: UUID,
        reason: StopReason,
    ) -> None:
        """Avisa del final sin que un fallo del oyente parezca un fallo del efecto."""
        if on_finished is None:
            return
        try:
            await on_finished(effect_id, reason)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("No se pudo notificar el final del efecto %s", effect_id)
