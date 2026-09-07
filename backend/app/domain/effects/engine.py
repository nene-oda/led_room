"""`EffectPlan`: la definicion ya resuelta contra un dispositivo concreto.

**Aqui se resuelve la autoridad entre `speed`, `transition_ms` y `fps`, una sola
vez** (NEXT_STEPS 6.3). Ningun renderer vuelve a mirar `speed` ni consulta la
configuracion: reciben pasos con la duracion, el brillo y el easing ya decididos.
Si cada renderer resolviera lo suyo, la regla tendria cuatro copias y bastaria
una para que dos efectos "a la misma velocidad" fueran a velocidades distintas.

```text
transition_ms  = duracion base autoritativa de UN segmento
speed          = multiplicador, NO una duracion
                 factor = 2 ** ((50 - speed) / 50)
                 0 -> x2.0 (lento) · 50 -> x1.0 · 100 -> x0.5 (rapido)
fps efectivos  = min(effect.fps, tope de despliegue)
duracion       = max(frame_duration_ms, round(transition_ms * factor))
```

Precedencia, tambien resuelta aqui: `speed` de la escena > `speed` del efecto;
`brightness` de la escena > `brightness` del paso > `max_brightness` del efecto.
Las anulaciones son parametros y no un tipo nuevo, para que la Fase 6 componga
un plan por objetivo de escena sin reimplementar nada.

El plan es **inmutable y de un solo uso logico**: no guarda progreso, no lee el
reloj y no toca el dispositivo. Todo lo temporal vive en el runner.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from backend.app.domain.devices.models import DeviceCapabilities
from backend.app.domain.devices.ports import DeviceCapabilityError
from backend.app.domain.effects.adaptation import missing_capabilities
from backend.app.domain.effects.frames import frame_duration_ms
from backend.app.domain.effects.models import (
    NEUTRAL_SPEED,
    ColorSpace,
    Easing,
    EffectDefinition,
    EffectType,
)
from backend.app.domain.effects.registry import renderer_for
from backend.app.domain.effects.renderers.base import EffectRenderer
from backend.app.domain.effects.segments import Segment
from backend.app.domain.lighting import RGBColor


def speed_factor(speed: int) -> float:
    """Multiplicador de duracion para una velocidad 0-100.

    Es exponencial y no lineal para que el control sea simetrico: 0 duplica la
    duracion, 100 la reduce a la mitad y 50 la deja igual. Con una recta, el
    extremo lento apenas se notaria y el rapido se volveria inutilizable.
    """
    return float(2.0 ** ((NEUTRAL_SPEED - speed) / NEUTRAL_SPEED))


@dataclass(frozen=True, slots=True)
class ResolvedStep:
    """Un vertice sin nada pendiente de decidir.

    Los `None` de `EffectStep` ya no existen aqui: un renderer que recibiera
    opcionales tendria que repetir la resolucion, y ahi es donde las copias
    divergen.
    """

    color: RGBColor
    brightness: int
    duration_ms: int
    easing: Easing


@dataclass(frozen=True, slots=True)
class EffectPlan:
    """Todo lo que hace falta para pintar, y nada mas."""

    effect_id: UUID
    type: EffectType
    renderer: EffectRenderer
    steps: tuple[ResolvedStep, ...]
    fps: int
    loop: bool
    color_space: ColorSpace
    min_brightness: int

    @property
    def frame_duration_ms(self) -> int:
        return frame_duration_ms(self.fps)

    def cycle(self) -> Iterator[Segment]:
        """Los segmentos de UN ciclo. Repetirlo es cosa del runner."""
        return self.renderer.segments(self)


def build_plan(
    definition: EffectDefinition,
    *,
    capabilities: DeviceCapabilities,
    max_fps: int,
    speed: int | None = None,
    brightness: int | None = None,
    color_space: ColorSpace = ColorSpace.HSV,
) -> EffectPlan:
    """Resuelve la definicion contra un dispositivo. **No escribe nada.**

    Lanza antes de que el runner exista, que es lo que garantiza el "cero
    `apply_frame`" cuando algo no cuadra:

    * `DeviceCapabilityError` (409) si falta un requisito duro del renderer;
    * `ValueError` (422) si el numero de pasos no encaja con el algoritmo.

    Las capacidades se validan **aqui y no en persistencia**: un efecto puede
    guardarse aunque hoy ningun dispositivo conectado lo soporte.
    """
    renderer = renderer_for(definition.type)

    missing = missing_capabilities(renderer.required_capabilities, capabilities)
    if missing:
        names = ", ".join(sorted(capability.value for capability in missing))
        raise DeviceCapabilityError(
            f"El dispositivo no soporta '{names}': no se puede reproducir el efecto "
            f"{definition.name!r} ({definition.type.value})."
        )

    _check_step_count(definition, renderer)

    fps = min(definition.fps, max_fps)
    factor = speed_factor(definition.speed if speed is None else speed)
    minimum_ms = frame_duration_ms(fps)
    base_ms = _scaled(definition.transition_ms, factor, minimum_ms)

    steps = tuple(
        ResolvedStep(
            color=step.color,
            # Precedencia: escena > paso > brillo base del efecto.
            brightness=_first_not_none(brightness, step.brightness, definition.max_brightness),
            duration_ms=(
                base_ms
                if step.duration_ms is None
                else _scaled(step.duration_ms, factor, minimum_ms)
            ),
            easing=step.easing or renderer.default_easing,
        )
        for step in definition.steps
    )

    return EffectPlan(
        effect_id=definition.id,
        type=definition.type,
        renderer=renderer,
        steps=steps,
        fps=fps,
        loop=definition.loop and renderer.loopable,
        color_space=color_space,
        min_brightness=min(definition.min_brightness, definition.max_brightness),
    )


def segment_stream(plan: EffectPlan) -> Iterator[Segment]:
    """Los segmentos que hay que pintar, repitiendo el ciclo si el efecto es en bucle.

    Es **una sola** secuencia continua, y no un ciclo generado de nuevo en cada
    vuelta, porque el generador de fotogramas necesita verla entera para emitir
    cada vertice una vez: el ultimo fotograma de una vuelta es el primero de la
    siguiente.
    """
    while True:
        yield from plan.cycle()
        if not plan.loop:
            return


def _check_step_count(definition: EffectDefinition, renderer: EffectRenderer) -> None:
    count = len(definition.steps)
    if count < renderer.min_steps:
        raise ValueError(
            f"El efecto {definition.type.value} necesita al menos {renderer.min_steps} "
            f"paso(s); se recibieron {count}."
        )
    if renderer.max_steps is not None and count > renderer.max_steps:
        raise ValueError(
            f"El efecto {definition.type.value} admite como mucho {renderer.max_steps} "
            f"paso(s); se recibieron {count}."
        )


def _scaled(duration_ms: int, factor: float, minimum_ms: int) -> int:
    """Aplica la velocidad sin que una duracion pueda quedar por debajo de un fotograma.

    Sin el suelo, `transition_ms = 0` o `1` producirian una duracion de 0 ms: el
    bucle intentaria emitir un fotograma de duracion nula y la linea de tiempo
    monotona avanzaria sin gastar tiempo.
    """
    return max(minimum_ms, round(duration_ms * factor))


def _first_not_none(*candidates: int | None) -> int:
    """Primer valor definido de una cadena de precedencia."""
    for candidate in candidates:
        if candidate is not None:
            return candidate
    raise AssertionError("La cadena de precedencia debe terminar en un valor concreto.")
