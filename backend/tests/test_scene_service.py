"""Casos de uso de escenas: atomicidad, delegacion y estado global.

Lo que se prueba aqui es la frontera de la Fase 6: quien decide que una escena no
se puede activar, **cuando** lo decide (antes de tocar el hardware, siempre) y
que el servicio no reimplementa nada de lo que ya hacen el reproductor y el
motor.

Reloj virtual en todos los casos: ningun test duerme de verdad.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from backend.app.application.effect_runner import EffectRunner
from backend.app.application.effect_service import EffectPlayer, EffectService
from backend.app.application.errors import NothingToActivateError, SceneNotFoundError
from backend.app.application.light_service import LightService
from backend.app.application.scene_service import SceneService
from backend.app.application.state_store import StateStore
from backend.app.domain.devices.models import SINGLE_COLOR_STRIP, DeviceCapabilities, DeviceStatus
from backend.app.domain.devices.ports import DeviceCapabilityError, DeviceNotConnectedError
from backend.app.domain.effects.models import EffectDefinition, EffectStep, EffectType
from backend.app.domain.lighting import RGBColor
from backend.app.domain.scenes.models import Scene, SceneTarget
from backend.tests.doubles import (
    ClockedLightDevice,
    InMemoryEffectRepository,
    InMemorySceneRepository,
    ManualClock,
    RecordingEventPublisher,
)

MORADO = RGBColor.from_hex("#7B00FF")
AZUL = RGBColor.from_hex("#009DFF")

SALON = UUID("11111111-1111-1111-1111-111111111111")
DORMITORIO = UUID("22222222-2222-2222-2222-222222222222")
COPIA = UUID("99999999-9999-9999-9999-999999999999")

SIN_RGB = DeviceCapabilities(
    rgb=False,
    brightness=True,
    effects=True,
    addressable=False,
    segments=False,
    white_channel=False,
    music_mode=False,
)


@pytest_asyncio.fixture(autouse=True)
async def sin_tareas_huerfanas() -> AsyncIterator[None]:
    yield
    vivas = [task for task in asyncio.all_tasks() if task.get_name().startswith("effect:")]
    assert not vivas, f"Quedaron tareas de efecto vivas: {vivas}"


def _efecto(
    *,
    effect_id: UUID | None = None,
    nombre: str = "Morado fijo",
    tipo: EffectType = EffectType.STATIC,
    colores: tuple[RGBColor, ...] = (MORADO,),
    **kwargs: object,
) -> EffectDefinition:
    return EffectDefinition(
        id=effect_id or uuid4(),
        name=nombre,
        type=tipo,
        steps=tuple(EffectStep(position=index, color=color) for index, color in enumerate(colores)),
        **kwargs,
    )


def _escena(*targets: SceneTarget, nombre: str = "Noche", scene_id: UUID | None = None) -> Scene:
    return Scene(id=scene_id or uuid4(), name=nombre, targets=targets)


class _Montaje:
    """Motor completo sobre reloj virtual, con el enlace ya abierto."""

    def __init__(
        self,
        *,
        scenes: Sequence[Scene] = (),
        effects: Sequence[EffectDefinition] = (),
        capabilities: DeviceCapabilities = SINGLE_COLOR_STRIP,
        connected: bool = True,
    ) -> None:
        self.clock = ManualClock()
        self.device = ClockedLightDevice(self.clock, capabilities=capabilities)
        self.publisher = RecordingEventPublisher()
        self.store = StateStore(self.publisher)
        self.runner = EffectRunner(self.device, self.clock)
        self.player = EffectPlayer(self.runner, self.store)
        self.repository = InMemorySceneRepository(scenes, effects=effects)
        self.service = SceneService(
            repository=self.repository,
            player=self.player,
            store=self.store,
            capabilities=capabilities,
            max_fps=20,
            new_id=lambda: COPIA,
        )
        # Las otras dos formas de quitarle el control a una escena: un comando
        # manual y un efecto suelto. Ambas comparten el MISMO reproductor, que es
        # lo que las convierte en preempcion y no en dos bucles a la vez.
        self.light = LightService(self.device, self.store, preempt=self.player.stop)
        self.effects = EffectService(
            repository=InMemoryEffectRepository(tuple(effects)),
            player=self.player,
            capabilities=capabilities,
            max_fps=20,
        )
        self._connected = connected

    async def preparar(self) -> None:
        if self._connected:
            async with self.store.mutate() as draft:
                draft.set_device(DeviceStatus(device_id=SALON, connected=True))

    async def hasta_que_pare(self) -> None:
        for _ in range(2000):
            if not self.runner.is_running:
                return
            await asyncio.sleep(0)
        raise AssertionError("El efecto no termino")


@pytest_asyncio.fixture
async def montaje() -> AsyncIterator[_Montaje]:
    efecto = _efecto()
    escena = _escena(SceneTarget(device_id=SALON, effect_id=efecto.id))
    montaje = _Montaje(scenes=[escena], effects=[efecto])
    await montaje.preparar()
    yield montaje
    await montaje.player.stop()


def _escena_de(montaje: _Montaje) -> Scene:
    return next(iter(montaje.repository.scenes.values()))


@pytest.mark.asyncio
async def test_activar_una_escena_reproduce_el_efecto_de_su_objetivo(montaje: _Montaje) -> None:
    escena = _escena_de(montaje)

    await montaje.service.activate(escena.id)
    await montaje.hasta_que_pare()

    assert montaje.device.colors == ["#7B00FF"]


@pytest.mark.asyncio
async def test_activar_una_escena_publica_scene_activated_despues_de_effect_started(
    montaje: _Montaje,
) -> None:
    """El orden no es cosmetico: la escena esta activa cuando su efecto ya suena."""
    escena = _escena_de(montaje)

    await montaje.service.activate(escena.id)

    assert montaje.publisher.types[:2] == ["effect.started", "scene.activated"]


@pytest.mark.asyncio
async def test_el_estado_global_recuerda_la_escena_y_el_efecto(montaje: _Montaje) -> None:
    escena = _escena_de(montaje)

    estado = await montaje.service.activate(escena.id)
    global_state = await montaje.store.snapshot()

    assert estado.id == escena.id
    assert global_state.scene is not None
    assert global_state.scene.id == escena.id
    assert global_state.effect is not None
    assert global_state.effect.running is True


@pytest.mark.asyncio
async def test_el_brillo_del_objetivo_manda_sobre_el_del_efecto() -> None:
    """`scene_target.brightness` > `effect_steps.brightness` > brillo base."""
    efecto = _efecto()
    escena = _escena(SceneTarget(device_id=SALON, effect_id=efecto.id, brightness=10))
    montaje = _Montaje(scenes=[escena], effects=[efecto])
    await montaje.preparar()

    await montaje.service.activate(escena.id)
    await montaje.hasta_que_pare()

    assert montaje.device.brightnesses == [10]


@pytest.mark.asyncio
async def test_la_velocidad_del_objetivo_manda_sobre_la_del_efecto() -> None:
    """`speed=100` es factor x0.5: la misma transicion dura la mitad, y con la
    mitad de fotogramas."""
    efecto = _efecto(
        tipo=EffectType.SMOOTH_CYCLE,
        colores=(MORADO, AZUL),
        transition_ms=1000,
        fps=20,
    )
    normal = _escena(SceneTarget(device_id=SALON, effect_id=efecto.id), nombre="Normal")
    rapida = _escena(
        SceneTarget(device_id=SALON, effect_id=efecto.id, speed=100),
        nombre="Rapida",
    )
    montaje = _Montaje(scenes=[normal, rapida], effects=[efecto])
    await montaje.preparar()

    await montaje.service.activate(normal.id)
    await montaje.hasta_que_pare()
    fotogramas_normales = len(montaje.device.frames)

    montaje.device.frames.clear()
    await montaje.service.activate(rapida.id)
    await montaje.hasta_que_pare()

    assert fotogramas_normales == 20
    assert len(montaje.device.frames) == 10


@pytest.mark.asyncio
async def test_un_objetivo_invalido_impide_que_arranque_el_valido() -> None:
    """Paso 3, atomico: media escena es peor que una escena rechazada.

    El objetivo valido va PRIMERO a proposito: si la validacion ocurriera dentro
    del bucle de arranque, ya estaria sonando cuando el segundo fallara.
    """
    bueno = _efecto()
    roto = _efecto(nombre="Ciclo de un color", tipo=EffectType.SMOOTH_CYCLE, colores=(AZUL,))
    escena = _escena(
        SceneTarget(device_id=SALON, effect_id=bueno.id),
        SceneTarget(device_id=DORMITORIO, effect_id=roto.id),
    )
    montaje = _Montaje(scenes=[escena], effects=[bueno, roto])
    await montaje.preparar()

    with pytest.raises(ValueError, match="necesita al menos 2 paso"):
        await montaje.service.activate(escena.id)

    assert montaje.device.frames == []
    assert montaje.runner.is_running is False
    estado = await montaje.store.snapshot()
    assert (estado.scene, estado.effect) == (None, None)


@pytest.mark.asyncio
async def test_un_objetivo_para_otro_dispositivo_rechaza_la_escena_entera() -> None:
    """El proceso mantiene UN enlace: activar solo la mitad dejaria media escena."""
    efecto = _efecto()
    escena = _escena(
        SceneTarget(device_id=SALON, effect_id=efecto.id),
        SceneTarget(device_id=DORMITORIO, effect_id=efecto.id),
    )
    montaje = _Montaje(scenes=[escena], effects=[efecto])
    await montaje.preparar()

    with pytest.raises(DeviceNotConnectedError, match=str(DORMITORIO)):
        await montaje.service.activate(escena.id)

    assert montaje.device.frames == []
    assert (await montaje.store.snapshot()).scene is None


@pytest.mark.asyncio
async def test_una_capacidad_ausente_rechaza_la_escena_sin_escribir_nada() -> None:
    """409 nombrando la capacidad que falta, con cero escrituras al adaptador."""
    efecto = _efecto()
    escena = _escena(SceneTarget(device_id=SALON, effect_id=efecto.id))
    montaje = _Montaje(scenes=[escena], effects=[efecto], capabilities=SIN_RGB)
    await montaje.preparar()

    with pytest.raises(DeviceCapabilityError, match="rgb"):
        await montaje.service.activate(escena.id)

    assert montaje.device.frames == []


@pytest.mark.asyncio
async def test_activar_sin_enlace_no_toca_el_adaptador() -> None:
    efecto = _efecto()
    escena = _escena(SceneTarget(device_id=SALON, effect_id=efecto.id))
    montaje = _Montaje(scenes=[escena], effects=[efecto], connected=False)
    await montaje.preparar()

    with pytest.raises(DeviceNotConnectedError):
        await montaje.service.activate(escena.id)

    assert montaje.device.frames == []


@pytest.mark.asyncio
async def test_una_escena_sin_objetivos_habilitados_no_es_activable() -> None:
    """409, no 404: la escena existe, pero no hay nada que reproducir."""
    efecto = _efecto()
    escena = _escena(SceneTarget(device_id=SALON, effect_id=efecto.id, enabled=False))
    montaje = _Montaje(scenes=[escena], effects=[efecto])
    await montaje.preparar()

    with pytest.raises(NothingToActivateError, match="Noche"):
        await montaje.service.activate(escena.id)


@pytest.mark.asyncio
async def test_activar_una_escena_inexistente_es_un_404(montaje: _Montaje) -> None:
    with pytest.raises(SceneNotFoundError):
        await montaje.service.activate(uuid4())


@pytest.mark.asyncio
async def test_activar_otra_escena_sustituye_a_la_anterior() -> None:
    """`EffectPlayer.start` cancela el bucle anterior y lo espera; aqui no se repite."""
    primero = _efecto(nombre="Morado")
    segundo = _efecto(nombre="Azul", colores=(AZUL,))
    noche = _escena(SceneTarget(device_id=SALON, effect_id=primero.id), nombre="Noche")
    dia = _escena(SceneTarget(device_id=SALON, effect_id=segundo.id), nombre="Dia")
    montaje = _Montaje(scenes=[noche, dia], effects=[primero, segundo])
    await montaje.preparar()

    await montaje.service.activate(noche.id)
    await montaje.hasta_que_pare()
    await montaje.service.activate(dia.id)
    await montaje.hasta_que_pare()

    estado = await montaje.store.snapshot()
    assert montaje.device.colors == ["#7B00FF", "#009DFF"]
    assert estado.scene is not None
    assert estado.scene.id == dia.id


@pytest.mark.asyncio
async def test_activar_otra_escena_sobre_una_que_sigue_sonando_deja_la_nueva() -> None:
    """La escena B no puede llevarse por delante su propia ranura recien puesta.

    Con efectos en bucle el anterior se cancela (no termina solo), asi que la
    unica limpieza posible es la de `start`: si soltara la escena sin saber que
    quien arranca es una activacion, `scene` acabaria a `None` en vez de en B.
    """
    primero = _efecto(
        nombre="Morado", tipo=EffectType.SMOOTH_CYCLE, colores=(MORADO, AZUL), loop=True
    )
    segundo = _efecto(
        nombre="Azul", tipo=EffectType.SMOOTH_CYCLE, colores=(AZUL, MORADO), loop=True
    )
    noche = _escena(SceneTarget(device_id=SALON, effect_id=primero.id), nombre="Noche")
    dia = _escena(SceneTarget(device_id=SALON, effect_id=segundo.id), nombre="Dia")
    montaje = _Montaje(scenes=[noche, dia], effects=[primero, segundo])
    await montaje.preparar()

    await montaje.service.activate(noche.id)
    await asyncio.sleep(0)
    await montaje.service.activate(dia.id)

    estado = await montaje.store.snapshot()
    assert estado.scene is not None
    assert estado.scene.id == dia.id
    assert estado.effect is not None
    assert estado.effect.id == segundo.id

    await montaje.player.stop()


@pytest.mark.asyncio
async def test_un_comando_manual_suelta_la_escena_y_el_efecto() -> None:
    """Preempcion: `scene` con `effect: null` describiria una escena que no suena."""
    efecto = _efecto(tipo=EffectType.SMOOTH_CYCLE, colores=(MORADO, AZUL), loop=True)
    escena = _escena(SceneTarget(device_id=SALON, effect_id=efecto.id))
    montaje = _Montaje(scenes=[escena], effects=[efecto])
    await montaje.preparar()

    await montaje.service.activate(escena.id)
    await asyncio.sleep(0)
    await montaje.light.set_color(AZUL)

    estado = await montaje.store.snapshot()
    assert (estado.scene, estado.effect) == (None, None)
    assert montaje.runner.is_running is False


@pytest.mark.asyncio
async def test_un_comando_manual_suelta_una_escena_cuyo_efecto_ya_termino(
    montaje: _Montaje,
) -> None:
    """La escena de un `STATIC` sobrevive a su efecto, pero no a un comando manual.

    Es el caso que la salida rapida de `EffectPlayer.stop` dejaba escapar: sin
    efecto y sin bucle vivo, la preempcion volvia sin mirar la escena.
    """
    escena = _escena_de(montaje)

    await montaje.service.activate(escena.id)
    await montaje.hasta_que_pare()
    await asyncio.sleep(0)
    # El efecto ya se agoto solo y aun asi la escena sigue puesta: la tira
    # muestra justo lo que la escena pidio.
    assert (await montaje.store.snapshot()).scene is not None

    await montaje.light.set_brightness(30)

    assert (await montaje.store.snapshot()).scene is None


@pytest.mark.asyncio
async def test_arrancar_un_efecto_suelto_suelta_la_escena() -> None:
    """El efecto suelto no pertenece a ninguna escena: la ranura debe vaciarse."""
    de_la_escena = _efecto(nombre="De la escena")
    suelto = _efecto(
        nombre="Suelto", tipo=EffectType.SMOOTH_CYCLE, colores=(AZUL, MORADO), loop=True
    )
    escena = _escena(SceneTarget(device_id=SALON, effect_id=de_la_escena.id))
    montaje = _Montaje(scenes=[escena], effects=[de_la_escena, suelto])
    await montaje.preparar()

    await montaje.service.activate(escena.id)
    await montaje.effects.start(suelto.id)

    estado = await montaje.store.snapshot()
    assert estado.scene is None
    assert estado.effect is not None
    assert estado.effect.id == suelto.id

    await montaje.player.stop()


@pytest.mark.asyncio
async def test_soltar_la_escena_se_difunde_como_snapshot() -> None:
    """Ningun evento congelado dice "la escena ya no esta activa".

    `effect.stopped` solo lleva el `effect_id`, asi que sin el snapshot un
    cliente que aplicara eventos se quedaria mostrando la escena para siempre.
    """
    efecto = _efecto(tipo=EffectType.SMOOTH_CYCLE, colores=(MORADO, AZUL), loop=True)
    escena = _escena(SceneTarget(device_id=SALON, effect_id=efecto.id))
    montaje = _Montaje(scenes=[escena], effects=[efecto])
    await montaje.preparar()

    await montaje.service.activate(escena.id)
    await asyncio.sleep(0)
    await montaje.light.set_color(AZUL)

    assert montaje.publisher.types[-3:] == [
        "effect.stopped",
        "state.snapshot",
        "light.color.changed",
    ]


@pytest.mark.asyncio
async def test_sin_escena_activa_la_preempcion_sigue_sin_gastar_version() -> None:
    """La ruta caliente del arrastre no puede pagar por una escena que no hay."""
    montaje = _Montaje()
    await montaje.preparar()
    version_inicial = (await montaje.store.snapshot()).version

    await montaje.player.stop()

    assert (await montaje.store.snapshot()).version == version_inicial
    assert montaje.publisher.types == []


@pytest.mark.asyncio
async def test_duplicar_una_escena_usa_el_identificador_del_servidor(montaje: _Montaje) -> None:
    escena = _escena_de(montaje)

    copia = montaje.service.duplicate(escena.id)

    assert copia.id == COPIA
    assert copia.name == "Noche (copia)"
    assert montaje.repository.get(COPIA) == copia


@pytest.mark.asyncio
async def test_duplicar_una_escena_inexistente_es_un_404(montaje: _Montaje) -> None:
    with pytest.raises(SceneNotFoundError):
        montaje.service.duplicate(uuid4())


@pytest.mark.asyncio
async def test_borrar_una_escena_inexistente_es_un_404(montaje: _Montaje) -> None:
    with pytest.raises(SceneNotFoundError):
        montaje.service.delete(uuid4())
