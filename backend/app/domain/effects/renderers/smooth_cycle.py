"""`SMOOTH_CYCLE`: recorrer una paleta con transiciones suaves.

* **Tira analogica RGB (hoy):** transiciones **temporales** encadenadas, con el
  vertice emitido una sola vez. La "mezcla de colores" del README es esto: la
  tira muestra un color a la vez.
* **Tira direccionable (futuro):** la misma paleta desplegada espacialmente con
  un desplazamiento temporal, sin cambiar la definicion persistida.

`Sunset`, `Cyberpunk`, `Gaming` y `America` son **filas** de este tipo con
paletas distintas, no codigo. `CUSTOM` tampoco es un renderer: es este mismo con
`duration_ms` y `easing` por paso.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import pairwise
from typing import TYPE_CHECKING

from backend.app.domain.effects.models import Capability, Easing
from backend.app.domain.effects.segments import Segment, TransitionSegment

if TYPE_CHECKING:  # pragma: no cover
    from backend.app.domain.effects.engine import EffectPlan, ResolvedStep


class SmoothCycleRenderer:
    required_capabilities: frozenset[Capability] = frozenset({Capability.RGB})
    #: Con un solo color no hay ninguna transicion que hacer: eso es un STATIC.
    min_steps: int = 2
    max_steps: int | None = None
    loopable: bool = True
    default_easing: Easing = Easing.LINEAR

    def segments(self, plan: EffectPlan) -> Iterator[Segment]:
        for current, following in _vertex_pairs(plan.steps, loop=plan.loop):
            yield TransitionSegment(
                start=current.color,
                end=following.color,
                start_brightness=current.brightness,
                end_brightness=following.brightness,
                # La duracion la fija el vertice del que se SALE: es lo que
                # permite que un paso concreto sea mas lento que el resto.
                duration_ms=current.duration_ms,
                easing=current.easing,
            )


def _vertex_pairs(
    steps: tuple[ResolvedStep, ...],
    *,
    loop: bool,
) -> Iterator[tuple[ResolvedStep, ResolvedStep]]:
    """Vertices consecutivos; con `loop`, cierra el ciclo volviendo al primero."""
    yield from pairwise(steps)
    if loop:
        yield steps[-1], steps[0]
