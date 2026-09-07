"""`BREATH`: respirar recorriendo una paleta.

Es `SMOOTH_CYCLE` y `PULSE` **compuestos**: el brillo baja sobre el color actual
y vuelve a subir ya sobre el siguiente, de modo que el cambio de color ocurre en
la parte oscura de la respiracion y no se ve como un corte.

* **Tira analogica RGB (hoy):** dos transiciones temporales por paso.
* **Tira direccionable (futuro):** un gradiente que respira.

No duplica ninguna aritmetica: la envolvente es la misma primitiva que usa
`PULSE` y los fotogramas los genera el unico generador de `frames.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from backend.app.domain.effects.models import Capability, Easing
from backend.app.domain.effects.renderers.base import breathing_segments
from backend.app.domain.effects.segments import Segment

if TYPE_CHECKING:  # pragma: no cover
    from backend.app.domain.effects.engine import EffectPlan


class BreathRenderer:
    required_capabilities: frozenset[Capability] = frozenset({Capability.RGB})
    #: Con un solo paso degenera en un `PULSE`, que es un resultado correcto y
    #: no un caso degenerado que haya que prohibir.
    min_steps: int = 1
    max_steps: int | None = None
    loopable: bool = True
    default_easing: Easing = Easing.EASE_IN_OUT

    def segments(self, plan: EffectPlan) -> Iterator[Segment]:
        yield from breathing_segments(plan.steps, loop=plan.loop, floor=plan.min_brightness)
