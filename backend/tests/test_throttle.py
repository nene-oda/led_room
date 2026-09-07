"""El limitador de ~20 act./s: ultimo valor gana con borde de salida (NEXT_STEPS 4.4).

Todo el tiempo de estos tests es **virtual**: `VirtualClock` sustituye al `sleep`
del limitador, asi que una rafaga de un segundo se ejecuta en microsegundos y sin
depender de la carga de la maquina. Un test de limitacion con `asyncio.sleep`
reales es lento y, sobre todo, intermitente.
"""

from __future__ import annotations

import asyncio
import heapq

import pytest

from backend.app.application.throttle import LastValueThrottle, LightThrottles
from backend.app.domain.lighting import RGBColor

#: 20 actualizaciones por segundo, que es `Settings.throttle_interval_ms` con los
#: valores por defecto (`LED_ROOM_BLE_MAX_UPDATES_PER_SECOND=20`).
INTERVAL_S = 0.05


class VirtualClock:
    """Planificador de tiempo virtual: `sleep` que solo avanza cuando se le pide."""

    def __init__(self) -> None:
        self.now = 0.0
        self._sleepers: list[tuple[float, int, asyncio.Future[None]]] = []
        self._sequence = 0

    async def sleep(self, delay: float) -> None:
        if delay <= 0:
            await asyncio.sleep(0)
            return

        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._sequence += 1
        heapq.heappush(self._sleepers, (self.now + delay, self._sequence, future))
        await future

    async def advance(self, delta: float) -> None:
        """Avanza el reloj y deja correr a las tareas que despiertan por el camino."""
        target = self.now + delta
        while self._sleepers and self._sleepers[0][0] <= target:
            deadline, _, future = heapq.heappop(self._sleepers)
            self.now = deadline
            if not future.done():
                future.set_result(None)
            await self._settle()

        self.now = target
        await self._settle()

    @staticmethod
    async def _settle() -> None:
        # Varias cesiones: la tarea despertada aplica el valor y vuelve a
        # dormirse, y ese ciclo puede atravesar mas de un punto de suspension.
        for _ in range(5):
            await asyncio.sleep(0)


class Applier:
    """Registra lo aplicado. `failure` simula un enlace caido a mitad del arrastre."""

    def __init__(self) -> None:
        self.applied: list[int] = []
        self.failure: Exception | None = None

    async def __call__(self, value: int) -> None:
        self.applied.append(value)
        if self.failure is not None:
            failure, self.failure = self.failure, None
            raise failure


@pytest.mark.asyncio
async def test_el_primer_valor_se_aplica_de_inmediato() -> None:
    """Borde de entrada: un arrastre debe verse ya, no dentro de 50 ms."""
    clock = VirtualClock()
    applier = Applier()
    throttle = LastValueThrottle(applier, interval_s=INTERVAL_S, sleep=clock.sleep)

    await throttle.submit(7)
    await clock.advance(0)

    assert applier.applied == [7]

    await throttle.cancel()


@pytest.mark.asyncio
async def test_una_rafaga_de_200_comandos_en_un_segundo_no_supera_21_escrituras() -> None:
    """El criterio de aceptacion de NEXT_STEPS 4.4, con el ultimo valor aplicado."""
    clock = VirtualClock()
    applier = Applier()
    throttle = LastValueThrottle(applier, interval_s=INTERVAL_S, sleep=clock.sleep)

    for value in range(200):
        await throttle.submit(value)
        await clock.advance(1.0 / 200)

    # Borde de salida: la ventana en curso se cierra y aplica lo pendiente.
    await clock.advance(INTERVAL_S)

    assert len(applier.applied) <= 21, applier.applied
    assert applier.applied[-1] == 199, "El ultimo comando de la rafaga debe aplicarse siempre"
    assert applier.applied == sorted(applier.applied), "Nunca se aplica un valor mas viejo"

    await throttle.cancel()


@pytest.mark.asyncio
async def test_el_valor_intermedio_se_descarta_sin_encolarse() -> None:
    """No hay cola: una cola de 200 colores obsoletos es justo lo que se evita."""
    clock = VirtualClock()
    applier = Applier()
    throttle = LastValueThrottle(applier, interval_s=INTERVAL_S, sleep=clock.sleep)

    await throttle.submit(1)
    await clock.advance(0)
    for value in (2, 3, 4, 5):
        await throttle.submit(value)
    await clock.advance(INTERVAL_S)

    assert applier.applied == [1, 5]

    await throttle.cancel()


@pytest.mark.asyncio
async def test_cancelar_descarta_lo_pendiente_y_cede_el_control() -> None:
    """Un comando manual (o una escena) toma el control sin competir con el arrastre."""
    clock = VirtualClock()
    applier = Applier()
    throttle = LastValueThrottle(applier, interval_s=INTERVAL_S, sleep=clock.sleep)

    await throttle.submit(1)
    await clock.advance(0)
    await throttle.submit(99)

    await throttle.cancel()
    await clock.advance(10 * INTERVAL_S)

    assert applier.applied == [1]


@pytest.mark.asyncio
async def test_cancelar_dos_veces_no_falla() -> None:
    clock = VirtualClock()
    throttle = LastValueThrottle(Applier(), interval_s=INTERVAL_S, sleep=clock.sleep)

    await throttle.submit(1)
    await throttle.cancel()
    await throttle.cancel()


@pytest.mark.asyncio
async def test_un_fallo_al_aplicar_no_mata_al_limitador() -> None:
    """Si el enlace se cae a mitad del arrastre, el siguiente color debe poder aplicarse."""
    clock = VirtualClock()
    applier = Applier()
    applier.failure = RuntimeError("escritura BLE fallida")
    throttle = LastValueThrottle(applier, interval_s=INTERVAL_S, sleep=clock.sleep)

    await throttle.submit(1)
    await clock.advance(0)
    await throttle.submit(2)
    await clock.advance(INTERVAL_S)

    assert applier.applied == [1, 2]

    await throttle.cancel()


@pytest.mark.asyncio
async def test_el_limitador_no_deja_tareas_de_fondo_al_cancelar() -> None:
    baseline = len(asyncio.all_tasks())
    clock = VirtualClock()
    throttle = LastValueThrottle(Applier(), interval_s=INTERVAL_S, sleep=clock.sleep)

    for value in range(10):
        await throttle.submit(value)
        await clock.advance(0.001)

    assert len(asyncio.all_tasks()) > baseline, "El test no habria probado nada sin tarea viva"

    await throttle.cancel()

    assert len(asyncio.all_tasks()) == baseline


@pytest.mark.asyncio
async def test_puede_limitar_colores_del_dominio() -> None:
    """El limitador es generico: la politica no depende de que valor se coalesce."""
    clock = VirtualClock()
    applied: list[RGBColor] = []

    async def apply(color: RGBColor) -> str:
        # Devuelve algo a proposito: `LightService.set_color` devuelve el
        # `LightState` y debe encajar sin adaptadores.
        applied.append(color)
        return color.to_hex()

    throttle = LastValueThrottle(apply, interval_s=INTERVAL_S, sleep=clock.sleep)

    await throttle.submit(RGBColor(r=255, g=0, b=0))
    await clock.advance(0)
    await throttle.submit(RGBColor(r=0, g=0, b=255))
    await clock.advance(INTERVAL_S)

    assert [color.to_hex() for color in applied] == ["#FF0000", "#0000FF"]

    await throttle.cancel()


def test_el_intervalo_debe_ser_positivo() -> None:
    with pytest.raises(ValueError, match="positivo"):
        LastValueThrottle(Applier(), interval_s=0)


@pytest.mark.asyncio
async def test_un_submit_concurrente_con_cancel_no_pierde_el_ultimo_valor() -> None:
    """I1: `cancel()` pisaba la tarea de un `submit` simultaneo.

    Reproducido: llega `light.brightness` (que cancela) y, en la misma vuelta del
    bucle, el ultimo `light.color` del arrastre. `cancel` esperaba a la tarea
    -- un punto de suspension -- y despues, en su `finally`, borraba
    `self._task`; el `submit` que se colo en medio vio la tarea vieja todavia
    asignada y no arranco ninguna. Quedaba `_pending=(99,)` con `_task=None`: el
    usuario soltaba el selector en morado y la tira se quedaba en el color
    anterior, para siempre.
    """
    applier = Applier()
    throttle = LastValueThrottle(applier, interval_s=INTERVAL_S)

    await throttle.submit(1)
    await asyncio.sleep(0)

    await asyncio.gather(throttle.cancel(), throttle.submit(99))
    await asyncio.sleep(2 * INTERVAL_S)

    assert applier.applied == [1, 99], "El valor posterior a la cancelacion debe aplicarse"

    await throttle.cancel()


@pytest.mark.asyncio
async def test_cancelar_sin_submit_concurrente_sigue_sin_dejar_nada_pendiente() -> None:
    """La otra mitad de I1: relanzar solo si de verdad llego algo nuevo."""
    applier = Applier()
    throttle = LastValueThrottle(applier, interval_s=INTERVAL_S)

    await throttle.submit(1)
    await asyncio.sleep(0)
    await throttle.submit(2)

    await throttle.cancel()
    await asyncio.sleep(2 * INTERVAL_S)

    assert applier.applied == [1]
    assert throttle._task is None


@pytest.mark.asyncio
async def test_los_dos_arrastres_son_independientes_y_el_encendido_cancela_ambos() -> None:
    """I3: el brillo tambien es un arrastre y necesita su propio limitador.

    Y son independientes: mover el brillo no puede descartar el color pendiente,
    porque son campos distintos del estado. Lo unico que invalida a los dos es el
    encendido.
    """
    clock = VirtualClock()
    colores: list[RGBColor] = []
    brillos = Applier()

    async def apply_color(color: RGBColor) -> None:
        colores.append(color)

    throttles = LightThrottles(
        color=LastValueThrottle(apply_color, interval_s=INTERVAL_S, sleep=clock.sleep),
        brightness=LastValueThrottle(brillos, interval_s=INTERVAL_S, sleep=clock.sleep),
    )

    rojo = RGBColor(r=255, g=0, b=0)
    azul = RGBColor(r=0, g=0, b=255)
    verde = RGBColor(r=0, g=255, b=0)

    await throttles.color.submit(rojo)
    await throttles.brightness.submit(10)
    await clock.advance(0)

    await throttles.color.submit(azul)
    await throttles.brightness.submit(20)
    await clock.advance(INTERVAL_S)

    assert colores == [rojo, azul]
    assert brillos.applied == [10, 20], "Un comando de color no puede tirar el brillo pendiente"

    await throttles.color.submit(verde)
    await throttles.brightness.submit(30)
    await throttles.cancel_all()
    await clock.advance(10 * INTERVAL_S)

    assert colores == [rojo, azul]
    assert brillos.applied == [10, 20]
