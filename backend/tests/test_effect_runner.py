"""Bucle de reproduccion: cadencia, descarte, cancelacion y desconexion.

**Ni un `asyncio.sleep` real.** Todo va contra `ManualClock`, asi que un efecto
de 4 s se verifica en microsegundos y dos ejecuciones dan lo mismo.

El otro invariante que vigila este modulo es que no queden tareas vivas: una
tarea de efecto huerfana sigue escribiendo por BLE despues de que el test que la
creo haya terminado.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from backend.app.application.effect_runner import EffectRunner, StopReason
from backend.app.domain.devices.models import SINGLE_COLOR_STRIP, DeviceCapabilities
from backend.app.domain.devices.ports import DeviceError, DeviceNotConnectedError
from backend.app.domain.effects.engine import EffectPlan, build_plan
from backend.app.domain.effects.models import EffectDefinition, EffectStep, EffectType
from backend.app.domain.lighting import RGBColor
from backend.tests.doubles import ClockedLightDevice, ManualClock

AZUL = RGBColor.from_hex("#009DFF")
MORADO = RGBColor.from_hex("#7B00FF")
ROSA = RGBColor.from_hex("#FF008C")

SIN_BRILLO = DeviceCapabilities(
    rgb=True,
    brightness=False,
    effects=True,
    addressable=False,
    segments=False,
    white_channel=False,
    music_mode=False,
)


@pytest_asyncio.fixture(autouse=True)
async def sin_tareas_huerfanas() -> AsyncIterator[None]:
    """Al terminar un test no puede quedar viva ninguna tarea de efecto.

    Es el guardian de "nunca se descarta una tarea sin esperarla": sin el, un
    `play()` que olvidara cancelar la anterior pasaria todos los demas tests.
    """
    yield
    vivas = [task for task in asyncio.all_tasks() if task.get_name().startswith("effect:")]
    assert not vivas, f"Quedaron tareas de efecto vivas: {vivas}"


def _plan(
    effect_type: EffectType = EffectType.SMOOTH_CYCLE,
    *,
    colores: tuple[RGBColor, ...] = (AZUL, MORADO),
    loop: bool = False,
    capabilities: DeviceCapabilities = SINGLE_COLOR_STRIP,
    effect_id: UUID | None = None,
    **kwargs: object,
) -> EffectPlan:
    definicion = EffectDefinition(
        id=effect_id or uuid4(),
        name="Prueba",
        type=effect_type,
        loop=loop,
        steps=tuple(EffectStep(position=index, color=color) for index, color in enumerate(colores)),
        **kwargs,
    )
    return build_plan(definicion, capabilities=capabilities, max_fps=20)


async def _hasta_que_pare(runner: EffectRunner) -> None:
    """Cede el control hasta que la tarea del efecto termine sola.

    Con reloj virtual no hay nada que esperar de verdad: cada `sleep` del motor
    es un `asyncio.sleep(0)`, asi que basta con dejar correr el bucle.
    """
    for _ in range(2000):
        if not runner.is_running:
            return
        await asyncio.sleep(0)
    raise AssertionError("El efecto no termino")


@pytest.mark.asyncio
async def test_un_efecto_estatico_aplica_un_unico_fotograma() -> None:
    """No consume enlace BLE: un color fijo es una sola escritura."""
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)

    await runner.play(_plan(EffectType.STATIC, colores=(AZUL,)))
    await _hasta_que_pare(runner)

    assert device.colors == ["#009DFF"]


@pytest.mark.asyncio
async def test_una_transicion_produce_los_fotogramas_de_la_formula() -> None:
    """4000 ms a 20 fps: 80 fotogramas, del origen exacto al destino exacto."""
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)

    await runner.play(_plan(transition_ms=4000))
    await _hasta_que_pare(runner)

    assert len(device.frames) == 80
    assert device.colors[0] == "#009DFF"
    assert device.colors[-1] == "#7B00FF"
    assert clock.now == pytest.approx(3.95)


@pytest.mark.asyncio
async def test_se_escribe_una_sola_vez_por_fotograma() -> None:
    """`apply_frame` existe justamente para que no sean dos escrituras."""
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)

    await runner.play(_plan(transition_ms=1000))
    await _hasta_que_pare(runner)

    assert all(operation.startswith("apply_frame:") for operation in device.operations)
    assert len(device.operations) == len(device.frames)


@pytest.mark.asyncio
async def test_reproducir_otro_efecto_cancela_el_anterior_y_lo_espera() -> None:
    """Tras `play(B)`, el adaptador no recibe ningun fotograma mas de A."""
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)
    llegado = asyncio.Event()

    async def parar_en_el_quinto(index: int) -> None:
        if index == 5:
            llegado.set()
            await asyncio.Event().wait()

    device.on_frame = parar_en_el_quinto
    await runner.play(_plan(colores=(AZUL, MORADO), loop=True, transition_ms=4000))
    await llegado.wait()

    device.on_frame = None
    aplicados_de_a = len(device.frames)
    await runner.play(_plan(EffectType.STATIC, colores=(ROSA,)))
    await _hasta_que_pare(runner)

    assert device.colors[aplicados_de_a:] == ["#FF008C"]


@pytest.mark.asyncio
async def test_cancelar_antes_del_primer_fotograma_no_escribe_nada() -> None:
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)

    await runner.play(_plan(loop=True, transition_ms=4000))
    await runner.stop()

    assert device.frames == []
    assert runner.is_running is False


@pytest.mark.asyncio
async def test_cancelar_a_mitad_deja_el_ultimo_fotograma_puesto() -> None:
    """El `finally` NO apaga: apagar produciria un parpadeo negro entre escenas."""
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)
    llegado = asyncio.Event()

    async def bloquear_en_el_decimo(index: int) -> None:
        if index == 10:
            llegado.set()
            await asyncio.Event().wait()

    device.on_frame = bloquear_en_el_decimo
    await runner.play(_plan(loop=True, transition_ms=4000))
    await llegado.wait()
    await runner.stop()

    assert len(device.frames) == 10
    assert "set_power:False" not in device.operations
    assert runner.is_running is False


@pytest.mark.asyncio
async def test_cancelar_cuando_ya_habia_terminado_es_una_operacion_vacia() -> None:
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)

    await runner.play(_plan(EffectType.STATIC, colores=(AZUL,)))
    await _hasta_que_pare(runner)
    await runner.stop()
    await runner.stop()

    assert len(device.frames) == 1


@pytest.mark.asyncio
async def test_una_cancelacion_no_avisa_del_final() -> None:
    """Quien cancela ya sabe por que; avisarle le haria publicar un evento de mas."""
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)
    avisos: list[tuple[UUID, StopReason]] = []

    async def anotar(effect_id: UUID, reason: StopReason) -> None:
        avisos.append((effect_id, reason))

    await runner.play(_plan(loop=True, transition_ms=4000), on_finished=anotar)
    await asyncio.sleep(0)
    await runner.stop()

    assert avisos == []


@pytest.mark.asyncio
async def test_un_efecto_que_se_agota_avisa_de_que_termino() -> None:
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)
    identificador = uuid4()
    avisos: list[tuple[UUID, StopReason]] = []

    async def anotar(effect_id: UUID, reason: StopReason) -> None:
        avisos.append((effect_id, reason))

    await runner.play(
        _plan(EffectType.STATIC, colores=(AZUL,), effect_id=identificador), on_finished=anotar
    )
    await _hasta_que_pare(runner)

    assert avisos == [(identificador, StopReason.COMPLETED)]


@pytest.mark.asyncio
async def test_una_desconexion_a_mitad_para_el_efecto_sin_reintentar() -> None:
    """Un enlace a medias con reintentos en bucle apretado empeora la reconexion."""
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)
    avisos: list[StopReason] = []

    async def caer_en_el_quinto(index: int) -> None:
        if index == 5:
            device.failure = DeviceNotConnectedError("el enlace se cayo")

    async def anotar(effect_id: UUID, reason: StopReason) -> None:
        avisos.append(reason)

    device.on_frame = caer_en_el_quinto
    await runner.play(_plan(loop=True, transition_ms=4000), on_finished=anotar)
    await _hasta_que_pare(runner)

    assert len(device.frames) == 5
    assert avisos == [StopReason.DISCONNECTED]


@pytest.mark.asyncio
async def test_un_fallo_de_escritura_para_el_efecto_en_ese_fotograma() -> None:
    """Un adaptador que falla en el quinto produce exactamente 5 escrituras."""
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)
    avisos: list[StopReason] = []

    async def fallar_en_el_quinto(index: int) -> None:
        if index == 5:
            device.failure = DeviceError("escritura rechazada")

    async def anotar(effect_id: UUID, reason: StopReason) -> None:
        avisos.append(reason)

    device.on_frame = fallar_en_el_quinto
    await runner.play(_plan(loop=True, transition_ms=4000), on_finished=anotar)
    await _hasta_que_pare(runner)

    assert len(device.frames) == 5
    assert avisos == [StopReason.DEVICE_ERROR]


@pytest.mark.asyncio
async def test_un_adaptador_lento_descarta_fotogramas_en_vez_de_acumular() -> None:
    """Adaptador a 3x el periodo, efecto de 1 s a 20 fps: ~7 aplicados, no 20.

    Y el ultimo aplicado es el destino del efecto: un fotograma atrasado no vale
    nada, pero el final si, porque es el que se queda encendido.
    """
    clock = ManualClock()
    device = ClockedLightDevice(clock, latency_s=0.150)
    runner = EffectRunner(device, clock)

    await runner.play(_plan(transition_ms=1000))
    await _hasta_que_pare(runner)

    assert 6 <= len(device.frames) <= 9
    assert device.colors[-1] == "#7B00FF"
    assert runner.dropped_frames > 0
    assert len(device.frames) + runner.dropped_frames == 20


@pytest.mark.asyncio
async def test_un_adaptador_rapido_no_descarta_nada() -> None:
    """Control positivo: sin retraso, se aplican los 20 fotogramas."""
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)

    await runner.play(_plan(transition_ms=1000))
    await _hasta_que_pare(runner)

    assert len(device.frames) == 20
    assert runner.dropped_frames == 0


@pytest.mark.asyncio
async def test_el_bucle_recorre_la_paleta_sin_repetir_el_vertice() -> None:
    clock = ManualClock()
    device = ClockedLightDevice(clock)
    runner = EffectRunner(device, clock)
    llegado = asyncio.Event()

    async def parar_al_dar_la_vuelta(index: int) -> None:
        if index == 60:
            llegado.set()
            await asyncio.Event().wait()

    device.on_frame = parar_al_dar_la_vuelta
    # Tres colores, 1000 ms cada transicion: 20 + 19 + 19 = 58 por vuelta.
    await runner.play(_plan(colores=(AZUL, MORADO, ROSA), loop=True, transition_ms=1000))
    await llegado.wait()
    await runner.stop()

    assert device.colors[57] == "#009DFF"
    assert device.colors[58] != "#009DFF"


@pytest.mark.asyncio
async def test_sin_control_de_brillo_el_fotograma_llega_degradado_al_adaptador() -> None:
    """La degradacion ocurre en el borde, no en la definicion persistida."""
    clock = ManualClock()
    device = ClockedLightDevice(clock, capabilities=SIN_BRILLO)
    runner = EffectRunner(device, clock)

    await runner.play(
        _plan(
            EffectType.STATIC,
            colores=(RGBColor(r=200, g=100, b=50),),
            max_brightness=50,
        )
    )
    await _hasta_que_pare(runner)

    assert device.colors == ["#643219"]
    assert device.brightnesses == [100]
