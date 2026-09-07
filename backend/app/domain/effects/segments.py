"""Unidad intermedia del render: el **segmento**, no el fotograma.

Un renderer produce segmentos; un unico generador (`frames.render_segments`) los
convierte en `LightFrame`. Asi la aritmetica de fps y la convencion de extremos
existen en **un solo sitio** y añadir un efecto no puede equivocarse en ellas
(NEXT_STEPS 6.3).

Un segmento describe intencion sobre el tiempo y no sabe nada de fps, del reloj
ni del dispositivo.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.effects.models import Easing
from backend.app.domain.lighting import Percent, RGBColor


class HoldSegment(BaseModel):
    """Mantener un color y un brillo durante un tiempo.

    Produce **un solo fotograma**, no uno por periodo: repetir la misma escritura
    a 20 fps gastaria el enlace BLE sin cambiar nada de lo que se ve. La duracion
    la respeta el bucle de reproduccion esperando antes del siguiente fotograma.
    """

    model_config = ConfigDict(frozen=True)

    color: RGBColor
    brightness: Percent
    duration_ms: int = Field(ge=0)


class TransitionSegment(BaseModel):
    """Ir de un vertice a otro, interpolando color y brillo a la vez.

    Los extremos son inclusivos: `t=0` da exactamente el origen y `t=1`
    exactamente el destino (ARCHITECTURE 3.5).
    """

    model_config = ConfigDict(frozen=True)

    start: RGBColor
    end: RGBColor
    start_brightness: Percent
    end_brightness: Percent
    duration_ms: int = Field(ge=0)
    easing: Easing = Easing.LINEAR


#: Lo que un renderer puede emitir. Union cerrada a proposito: el generador de
#: fotogramas hace `match` sobre ella y mypy comprueba la exhaustividad.
Segment = HoldSegment | TransitionSegment
