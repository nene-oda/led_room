"""El contrato que cumple todo algoritmo de efecto.

Un renderer **no produce fotogramas**: produce segmentos, y describe **un solo
ciclo**. El bucle lo gestiona el runner y la aritmetica de fps vive en
`frames.py`. Asi añadir un efecto no puede equivocarse en los extremos ni
duplicar la formula (NEXT_STEPS 6.3).

Los cuatro atributos de clase son declarativos a proposito: sustituyen a los
`if type == ...` que, repartidos por el motor, acaban formando el switch gigante.
Cada uno existe por un motivo concreto:

* `required_capabilities` — que hardware necesita. Se comprueba al construir el
  plan; si falta algo, cero escrituras y 409.
* `min_steps` / `max_steps` — cuantos vertices admite. Hace irrepresentable un
  `SMOOTH_CYCLE` de un solo color o un `STATIC` de tres.
* `loopable` — si repetir el ciclo significa algo. Un `STATIC` en bucle solo
  reescribiria el mismo color para siempre.
* `default_easing` — la curva natural del algoritmo. Un `PULSE` lineal parece
  mecanico; que lo decida el renderer evita un `match` en el constructor del plan.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from backend.app.domain.effects.models import Capability, Easing
from backend.app.domain.effects.segments import Segment, TransitionSegment

if TYPE_CHECKING:  # pragma: no cover - solo para el tipo, evita un ciclo de imports
    from backend.app.domain.effects.engine import EffectPlan, ResolvedStep


@runtime_checkable
class EffectRenderer(Protocol):
    """Traduce un plan ya resuelto en los segmentos de UN ciclo."""

    required_capabilities: frozenset[Capability]
    min_steps: int
    max_steps: int | None
    loopable: bool
    default_easing: Easing

    def segments(self, plan: EffectPlan) -> Iterator[Segment]:
        """Un ciclo completo. Devuelve un iterador: un ciclo largo no se materializa."""
        ...


def breathing_segments(
    steps: tuple[ResolvedStep, ...],
    *,
    loop: bool,
    floor: int,
) -> Iterator[Segment]:
    """Bajar el brillo hasta `floor` y volver a subirlo, opcionalmente cambiando de color.

    Es la primitiva que comparten `PULSE` (un color) y `BREATH` (una paleta):
    la diferencia entre ambos es cuantos vertices admiten, no como respiran, y
    duplicar esta funcion en los dos renderers dejaria que se desincronizaran.

    Cada paso produce dos segmentos, cada uno de la duracion resuelta del paso:
    el efecto se apaga sobre el color actual y vuelve a encenderse ya sobre el
    siguiente. Sin bucle, el ultimo paso vuelve a si mismo, de modo que el efecto
    termina encendido y no a media respiracion.
    """
    total = len(steps)
    for index, current in enumerate(steps):
        has_next = loop or index + 1 < total
        following = steps[(index + 1) % total] if has_next else current
        bottom = min(floor, current.brightness, following.brightness)

        yield TransitionSegment(
            start=current.color,
            end=current.color,
            start_brightness=current.brightness,
            end_brightness=bottom,
            duration_ms=current.duration_ms,
            easing=current.easing,
        )
        yield TransitionSegment(
            start=current.color,
            end=following.color,
            start_brightness=bottom,
            end_brightness=following.brightness,
            duration_ms=current.duration_ms,
            easing=current.easing,
        )
