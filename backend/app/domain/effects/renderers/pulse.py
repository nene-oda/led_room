"""`PULSE`: un color fijo cuyo brillo sube y baja.

* **Tira analogica RGB (hoy):** el color no cambia; el brillo va del techo del
  paso al suelo (`min_brightness`) y vuelve. `EASE_IN_OUT` por defecto, porque
  una rampa lineal parece mecanica.
* **Tira direccionable (futuro):** una onda que recorre la tira, con la misma
  envolvente y sin tocar este archivo.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from backend.app.domain.effects.models import Capability, Easing
from backend.app.domain.effects.renderers.base import breathing_segments
from backend.app.domain.effects.segments import Segment

if TYPE_CHECKING:  # pragma: no cover
    from backend.app.domain.effects.engine import EffectPlan


class PulseRenderer:
    """Un solo color. La envolvente la comparte con `BREATH`.

    Que ambos usen `breathing_segments` no los hace redundantes: `PULSE` fija un
    color y `BREATH` recorre una paleta, y esa diferencia se declara aqui con
    `max_steps`, no repitiendo la aritmetica de la envolvente.
    """

    required_capabilities: frozenset[Capability] = frozenset({Capability.RGB})
    min_steps: int = 1
    max_steps: int | None = 1
    loopable: bool = True
    default_easing: Easing = Easing.EASE_IN_OUT

    def segments(self, plan: EffectPlan) -> Iterator[Segment]:
        # `loop=False`: con un unico paso, cerrar el ciclo y no cerrarlo dan lo
        # mismo (el paso siguiente seria el propio paso), y el bucle ya lo repite
        # el runner.
        yield from breathing_segments(plan.steps, loop=False, floor=plan.min_brightness)
