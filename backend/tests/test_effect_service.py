"""Casos de uso de efectos: estado global, eventos, preempcion y persistencia cero.

Lo que se prueba aqui es la frontera entre el motor y el resto del sistema: quien
publica `effect.started`/`effect.stopped`, quien vacia la ranura del estado
global y quien cede el control cuando el usuario toca la luz a mano.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from backend.app.application.effect_runner import EffectRunner
from backend.app.application.effect_service import EffectPlayer, EffectService
from backend.app.application.errors import EffectNotFoundError
from backend.app.application.light_service import LightService
from backend.app.application.state_store import StateStore
from backend.app.domain.devices.models import SINGLE_COLOR_STRIP, DeviceCapabilities, DeviceStatus
from backend.app.domain.devices.ports import DeviceCapabilityError, DeviceNotConnectedError
from backend.app.domain.effects.models import EffectDefinition, EffectStep, EffectType
from backend.app.domain.lighting import RGBColor
from backend.tests.doubles import (
    ClockedLightDevice,
    InMemoryEffectRepository,
    ManualClock,
    RecordingEventPublisher,
)

AZUL = RGBColor.from_hex("#009DFF")
MORADO = RGBColor.from_hex("#7B00FF")
ROSA = RGBColor.from_hex("#FF008C")
DEVICE_ID = UUID("11111111-2222-3333-4444-555555555555")

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
    effect_type: EffectType = EffectType.SMOOTH_CYCLE,
    *,
    colores: tuple[RGBColor, ...] = (AZUL, MORADO),
    effect_id: UUID | None = None,
    nombre: str = "Prueba",
    **kwargs: object,
) -> EffectDefinition:
    return EffectDefinition(
        id=effect_id or uuid4(),
        name=nombre,
        type=effect_type,
        steps=tuple(EffectStep(position=index, color=color) for index, color in enumerate(colores)),
        **kwargs,
    )


class _Montaje:
    """Motor completo sobre reloj virtual, con el enlace ya abierto."""

    def __init__(
        self,
        efectos: tuple[EffectDefinition, ...] = (),
        *,
        capabilities: DeviceCapabilities = SINGLE_COLOR_STRIP,
        connected: bool = True,
    ) -> None:
        self.clock = ManualClock()
        self.device = ClockedLightDevice(self.clock, capabilities=capabilities)
        self.publisher = RecordingEventPublisher()
        self.store = StateStore(self.publisher)
        self.runner = EffectRunner(self.device, self.clock)
        self.player = EffectPlayer(self.runner, self.store)
        self.repository = InMemoryEffectRepository(efectos)
        self.service = EffectService(
            repository=self.repository,
            player=self.player,
            capabilities=capabilities,
            max_fps=20,
        )
        self.light = LightService(self.device, self.store, preempt=self.player.stop)
        self._connected = connected

    async def preparar(self) -> None:
        if self._connected:
            async with self.store.mutate() as draft:
                draft.set_device(DeviceStatus(device_id=DEVICE_ID, connected=True))

    async def hasta_que_pare(self) -> None:
        for _ in range(2000):
            if not self.runner.is_running:
                return
            await asyncio.sleep(0)
        raise AssertionError("El efecto no termino")


@pytest.mark.asyncio
async def test_arrancar_un_efecto_lo_publica_y_lo_deja_en_el_estado_global() -> None:
    efecto = _efecto(loop=True, transition_ms=4000)
    montaje = _Montaje((efecto,))
    await montaje.preparar()

    status = await montaje.service.start(efecto.id)

    assert status.running is True
    assert (await montaje.store.snapshot()).effect == status
    assert montaje.publisher.types[-1] == "effect.started"

    await montaje.player.stop()


@pytest.mark.asyncio
async def test_pararlo_vacia_la_ranura_y_publica_el_evento_de_parada() -> None:
    efecto = _efecto(loop=True, transition_ms=4000)
    montaje = _Montaje((efecto,))
    await montaje.preparar()

    await montaje.service.start(efecto.id)
    await montaje.service.stop(efecto.id)

    assert (await montaje.store.snapshot()).effect is None
    assert montaje.publisher.types[-1] == "effect.stopped"


@pytest.mark.asyncio
async def test_pararlo_dos_veces_no_publica_dos_paradas() -> None:
    """Sin cambio de estado no hay `version` nueva ni evento (ARCHITECTURE 4.5)."""
    efecto = _efecto(loop=True, transition_ms=4000)
    montaje = _Montaje((efecto,))
    await montaje.preparar()

    await montaje.service.start(efecto.id)
    await montaje.service.stop(efecto.id)
    await montaje.service.stop(efecto.id)

    assert montaje.publisher.types.count("effect.stopped") == 1


@pytest.mark.asyncio
async def test_parar_por_id_no_toca_al_efecto_que_lo_sustituyo() -> None:
    """Parar el viejo apagaria el que el usuario acaba de arrancar."""
    viejo = _efecto(loop=True, transition_ms=4000, nombre="Viejo")
    nuevo = _efecto(loop=True, transition_ms=4000, nombre="Nuevo")
    montaje = _Montaje((viejo, nuevo))
    await montaje.preparar()

    await montaje.service.start(viejo.id)
    await montaje.service.start(nuevo.id)
    await montaje.service.stop(viejo.id)

    efecto_activo = (await montaje.store.snapshot()).effect
    assert efecto_activo is not None
    assert efecto_activo.id == nuevo.id

    await montaje.player.stop()


@pytest.mark.asyncio
async def test_un_efecto_que_termina_solo_vacia_la_ranura() -> None:
    """Un STATIC dura un fotograma: el estado no puede quedarse diciendo que suena."""
    efecto = _efecto(EffectType.STATIC, colores=(AZUL,))
    montaje = _Montaje((efecto,))
    await montaje.preparar()

    await montaje.service.start(efecto.id)
    await montaje.hasta_que_pare()
    await asyncio.sleep(0)

    assert (await montaje.store.snapshot()).effect is None
    assert montaje.publisher.types[-1] == "effect.stopped"


@pytest.mark.asyncio
async def test_el_evento_de_arranque_llega_antes_que_el_de_parada() -> None:
    """El estado se marca ANTES de crear la tarea, o el orden se invierte."""
    efecto = _efecto(EffectType.STATIC, colores=(AZUL,))
    montaje = _Montaje((efecto,))
    await montaje.preparar()

    await montaje.service.start(efecto.id)
    await montaje.hasta_que_pare()
    await asyncio.sleep(0)

    assert montaje.publisher.types[-2:] == ["effect.started", "effect.stopped"]


@pytest.mark.asyncio
async def test_sin_enlace_no_se_arranca_ningun_efecto() -> None:
    efecto = _efecto()
    montaje = _Montaje((efecto,), connected=False)

    with pytest.raises(DeviceNotConnectedError):
        await montaje.service.start(efecto.id)

    assert montaje.device.frames == []
    assert montaje.publisher.events == []


@pytest.mark.asyncio
async def test_sin_la_capacidad_dura_se_rechaza_sin_una_sola_escritura() -> None:
    """409 al construir el plan: cero `apply_frame` (NEXT_STEPS 6.8)."""
    efecto = _efecto()
    montaje = _Montaje((efecto,), capabilities=SIN_RGB)
    await montaje.preparar()

    with pytest.raises(DeviceCapabilityError):
        await montaje.service.start(efecto.id)

    assert montaje.device.frames == []
    assert (await montaje.store.snapshot()).effect is None


@pytest.mark.asyncio
async def test_un_efecto_con_pasos_insuficientes_se_rechaza_sin_escribir() -> None:
    efecto = _efecto(colores=(AZUL,))
    montaje = _Montaje((efecto,))
    await montaje.preparar()

    with pytest.raises(ValueError, match="al menos 2"):
        await montaje.service.start(efecto.id)

    assert montaje.device.frames == []


@pytest.mark.asyncio
async def test_un_comando_manual_de_color_cancela_el_efecto_activo() -> None:
    """Sin preempcion, el siguiente fotograma pisaria el color del usuario."""
    efecto = _efecto(loop=True, transition_ms=4000)
    montaje = _Montaje((efecto,))
    await montaje.preparar()

    await montaje.service.start(efecto.id)
    await asyncio.sleep(0)
    await montaje.light.set_color(ROSA)

    assert montaje.runner.is_running is False
    assert (await montaje.store.snapshot()).effect is None
    assert (await montaje.store.snapshot()).light.color == ROSA
    assert montaje.device.operations[-1] == "set_color:255,0,140"


@pytest.mark.asyncio
async def test_un_encendido_manual_tambien_cancela_el_efecto() -> None:
    efecto = _efecto(loop=True, transition_ms=4000)
    montaje = _Montaje((efecto,))
    await montaje.preparar()

    await montaje.service.start(efecto.id)
    await asyncio.sleep(0)
    await montaje.light.set_power(False)

    assert montaje.runner.is_running is False
    assert montaje.publisher.types[-2:] == ["effect.stopped", "light.power.changed"]


@pytest.mark.asyncio
async def test_un_comando_rechazado_no_cancela_el_efecto() -> None:
    """Cancelar y responder 409 dejaria la tira parada por un comando invalido."""
    efecto = _efecto(loop=True, transition_ms=4000)
    montaje = _Montaje(
        (efecto,), capabilities=SINGLE_COLOR_STRIP.model_copy(update={"brightness": False})
    )
    await montaje.preparar()

    await montaje.service.start(efecto.id)
    await asyncio.sleep(0)

    with pytest.raises(DeviceCapabilityError):
        await montaje.light.set_brightness(40)

    assert montaje.runner.is_running is True
    await montaje.player.stop()


@pytest.mark.asyncio
async def test_sin_efecto_activo_la_preempcion_no_cambia_el_estado() -> None:
    """Es la ruta caliente del arrastre: no puede publicar nada ni gastar version."""
    montaje = _Montaje()
    await montaje.preparar()
    version_inicial = (await montaje.store.snapshot()).version

    await montaje.player.stop()

    assert (await montaje.store.snapshot()).version == version_inicial


@pytest.mark.asyncio
async def test_reproducir_no_escribe_nada_en_el_repositorio() -> None:
    """Cero escrituras por fotograma: los frames no se persisten jamas."""
    efecto = _efecto(transition_ms=4000)
    montaje = _Montaje((efecto,))
    await montaje.preparar()
    catalogo = dict(montaje.repository.effects)

    await montaje.service.start(efecto.id)
    await montaje.hasta_que_pare()

    assert len(montaje.device.frames) == 80
    assert montaje.repository.effects == catalogo


@pytest.mark.asyncio
async def test_arrancar_un_efecto_inexistente_es_un_404_de_dominio() -> None:
    montaje = _Montaje()
    await montaje.preparar()

    with pytest.raises(EffectNotFoundError):
        await montaje.service.start(uuid4())


def test_el_catalogo_se_lista_por_nombre() -> None:
    montaje = _Montaje((_efecto(nombre="Zeta"), _efecto(nombre="Alfa")))

    assert [efecto.name for efecto in montaje.service.list_effects()] == ["Alfa", "Zeta"]


def test_guardar_no_valida_capacidades() -> None:
    """Un efecto puede guardarse aunque hoy ningun dispositivo lo soporte."""
    montaje = _Montaje(capabilities=SIN_RGB)
    efecto = _efecto()

    assert montaje.service.save(efecto) == efecto


def test_borrar_algo_que_no_existe_es_un_404_de_dominio() -> None:
    montaje = _Montaje()

    with pytest.raises(EffectNotFoundError):
        montaje.service.delete(uuid4())
