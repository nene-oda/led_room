"""Limitador de actualizaciones: ultimo valor gana, con borde de salida.

Es **politica de producto**, no correccion de concurrencia. La otra pieza,
`infrastructure/devices/serialized.py`, garantiza que solo haya una escritura en
vuelo sobre el enlace; esta decide cuantas actualizaciones por segundo se le
permiten al usuario y **descarta** las intermedias. Mezclarlas produciria un
limitador que tambien serializa y un serializador que tambien descarta: nadie
sabria cual de los dos se comio una escritura (ARCHITECTURE 4, NEXT_STEPS A2).

Semantica (NEXT_STEPS 4.4):

* **Borde de entrada**: el primer valor tras un periodo inactivo se aplica ya.
  Un arrastre debe verse de inmediato.
* **Borde de salida**: el ultimo valor recibido se aplica SIEMPRE, aunque llegue
  dentro de la ventana. Un limitador que descarte el ultimo evento de un
  arrastre deja la tira en un color equivocado.
* **Sin cola**: hay un unico "valor pendiente" que se sobreescribe. Una cola de
  200 colores obsoletos es exactamente el problema a evitar.

Vive en la capa de aplicacion y no en el router del WebSocket: cuando llegue el
motor de efectos habra dos escritores compitiendo y un limitador metido en el
router solo veria uno (NEXT_STEPS 4.7).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from backend.app.domain.lighting import RGBColor

logger = logging.getLogger(__name__)


async def _default_sleep(delay: float) -> None:
    await asyncio.sleep(delay)


class LastValueThrottle[T]:
    """Coalescedor de un unico valor pendiente.

    Generico porque el valor no es asunto suyo: hoy se usa con `RGBColor` para
    el arrastre del selector, y el mismo objeto sirve para el brillo sin
    duplicar la politica.

    La operacion a aplicar se inyecta como funcion (`Callable`, no un awaitable
    ya construido): un valor descartado no debe dejar corrutinas creadas y nunca
    esperadas. Y el resultado se ignora a proposito (`Awaitable[object]`), de
    modo que `LightService.set_color`, que devuelve el `LightState`, encaja sin
    adaptadores.
    """

    def __init__(
        self,
        apply: Callable[[T], Awaitable[object]],
        *,
        interval_s: float,
        sleep: Callable[[float], Awaitable[None]] = _default_sleep,
    ) -> None:
        """Compone el limitador.

        `interval_s` sale de `settings.throttle_interval_ms / 1000`: la
        conversion de Hz a milisegundos ya vive en `Settings` y no se repite
        aqui.

        `sleep` se inyecta para que los tests midan la ventana en tiempo virtual
        y sean deterministas. No hace falta ademas un reloj: el limitador no
        hace aritmetica de plazos, solo duerme el intervalo entre aplicaciones,
        asi que no hay ninguna lectura de tiempo que falsear.
        """
        if interval_s <= 0:
            raise ValueError(f"El intervalo debe ser positivo; se recibio {interval_s}")

        self._apply = apply
        self._interval_s = interval_s
        self._sleep = sleep
        #: Tupla de un elemento, no una lista: el tipo mismo impide que el
        #: "valor pendiente" degenere en una cola.
        self._pending: tuple[T] | None = None
        self._task: asyncio.Task[None] | None = None

    async def submit(self, value: T) -> None:
        """Registra el valor mas reciente. No espera a que se aplique.

        Nunca bloquea el bucle de eventos ni al llamante: un arrastre a 120 Hz
        debe poder seguir emitiendo mientras la escritura anterior viaja por
        BLE.
        """
        self._pending = (value,)
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def cancel(self) -> None:
        """Descarta lo pendiente y detiene el aplicador. Idempotente.

        Es lo que permite que un comando manual (o una escena) tome el control
        de inmediato en vez de competir con los ultimos coletazos de un
        arrastre. Tambien es el cierre ordenado: al terminar, no queda ninguna
        tarea de fondo viva.

        El estado se limpia **antes** del `await`, no en un `finally` despues.
        Esperar a la tarea es un punto de suspension, y un `submit` que llegue
        durante esa espera veria `self._task` todavia asignado, no arrancaria
        ninguna tarea y despues el `finally` le borraria la suya: quedaba un
        valor pendiente que no se aplicaba nunca. En la practica, soltar el
        selector de color en morado justo cuando llega un `light.brightness`
        dejaba la tira en el color anterior. Por eso, al final, si aparecio un
        pendiente durante la espera, se relanza el aplicador.
        """
        self._pending = None
        task, self._task = self._task, None
        if task is None:
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            # Cancelacion pedida por nosotros, no del llamante: se absorbe.
            if asyncio.current_task() is task:  # pragma: no cover - defensivo
                raise

        self._restart_if_pending()

    def _restart_if_pending(self) -> None:
        """Relanza el aplicador si un `submit` se colo durante la cancelacion.

        Metodo aparte, y no un `if` en linea dentro de `cancel`: alli el
        analizador estatico da por hecho que `self._pending` sigue valiendo
        `None` porque no ve que otra corrutina lo escriba mientras se espera a la
        tarea, que es exactamente el fallo que este codigo corrige.
        """
        if self._pending is not None and self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        """Aplica el pendiente y duerme el intervalo, hasta quedarse sin trabajo.

        Aplicar ANTES de dormir da el borde de entrada; volver a comprobar el
        pendiente DESPUES de dormir da el de salida. Entre la comprobacion final
        y el `finally` no hay ningun punto de suspension, asi que un `submit`
        que llegue justo entonces encuentra `self._task` ya a `None` y arranca
        una tarea nueva: ningun valor se pierde.
        """
        try:
            while self._pending is not None:
                (value,) = self._pending
                self._pending = None
                await self._apply_once(value)
                await self._sleep(self._interval_s)
        finally:
            self._task = None

    async def _apply_once(self, value: T) -> None:
        """Un fallo al aplicar no puede matar al limitador.

        Quien llamo a `submit` ya recibio el control, asi que no hay nadie a
        quien devolverle la excepcion. Se registra y se sigue: si el enlace BLE
        se cae a mitad de un arrastre, el siguiente valor debe poder aplicarse
        en cuanto vuelva. Para avisar al usuario, componer: envolver `apply` con
        una funcion que publique el evento `error` (NEXT_STEPS A6) en vez de
        añadir un gancho aqui.
        """
        try:
            await self._apply(value)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("No se pudo aplicar el valor limitado %r", value)


@dataclass(frozen=True, slots=True)
class LightThrottles:
    """Los dos controles de arrastre de la luz, cada uno con su limitador.

    El color y el brillo se manipulan con sendos deslizadores, y **los dos** son
    arrastres: un deslizador de brillo genera igual de facil 200 eventos por
    segundo que el selector de color. Sin limitador propio, cada uno de esos
    eventos era una escritura BLE serializada con hasta 5 s de timeout, que es
    exactamente la "cola de 200 valores obsoletos" que este modulo existe para
    evitar.

    Son limitadores **independientes**: color y brillo son campos distintos del
    estado y mover uno no invalida el valor pendiente del otro. Lo que si los
    invalida a ambos es el encendido, y por eso `cancel_all` vive aqui: es la
    unica regla compartida, y repetirla en el router HTTP y en el del WebSocket
    la dejaria divergir.
    """

    color: LastValueThrottle[RGBColor]
    brightness: LastValueThrottle[int]

    async def cancel_all(self) -> None:
        """Un apagado (o el cierre del proceso) descarta los dos arrastres.

        Un color o un brillo pendiente aplicado despues de un apagado volveria a
        encender la tira.
        """
        await self.color.cancel()
        await self.brightness.cancel()
