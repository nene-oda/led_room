"""`STATIC`: un color fijo.

* **Tira analogica RGB (hoy):** un unico `HoldSegment`, es decir **un solo
  fotograma**. No consume enlace BLE mientras dura.
* **Tira direccionable (futuro):** el mismo color en todos los pixeles, con la
  misma definicion persistida y sin tocar este archivo.

Resuelve ademas el `scene_targets.effect_id NOT NULL` del esquema: una escena de
color fijo es un `STATIC` de un paso, no un caso especial en la activacion.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from backend.app.domain.effects.models import Capability, Easing
from backend.app.domain.effects.segments import HoldSegment, Segment

if TYPE_CHECKING:  # pragma: no cover
    from backend.app.domain.effects.engine import EffectPlan


class StaticRenderer:
    """Cumple `EffectRenderer` de forma estructural, sin heredar de nada."""

    required_capabilities: frozenset[Capability] = frozenset({Capability.RGB})
    min_steps: int = 1
    max_steps: int | None = 1
    #: Repetir un color fijo solo gastaria escrituras: no hay nada que animar.
    loopable: bool = False
    default_easing: Easing = Easing.LINEAR

    def segments(self, plan: EffectPlan) -> Iterator[Segment]:
        step = plan.steps[0]
        yield HoldSegment(
            color=step.color,
            brightness=step.brightness,
            duration_ms=step.duration_ms,
        )
