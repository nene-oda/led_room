"""Segmentos -> `LightFrame`. **El unico sitio con aritmetica de fps.**

Formula congelada (ARCHITECTURE 3.5, NEXT_STEPS 6.3):

```text
frame_duration_ms = round(1000 / fps)
frames            = max(1, round(duration_ms / 1000 * fps))
t_i               = i / (frames - 1)     # t=0 -> origen, t=1 -> destino
frames == 1       -> t = 1.0             # se emite el destino, nunca el origen
```

Con `transition_ms = 4000` y `fps = 20` salen **80** fotogramas de **50 ms**,
que es el ejemplo del README 12.

**El vertice se emite una sola vez.** Al encadenar segmentos, el ultimo
fotograma de uno y el primero del siguiente son el mismo instante: emitir los dos
produce un micro-tartamudeo en cada vertice y en cada vuelta del bucle. Por eso
el generador recibe la secuencia **entera** -- incluidas las repeticiones del
bucle -- y no un segmento suelto: es lo que le permite saber cual es el primero.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from backend.app.domain.effects.interpolators import (
    ease,
    interpolate_brightness,
    interpolate_color,
)
from backend.app.domain.effects.models import ColorSpace
from backend.app.domain.effects.segments import HoldSegment, Segment, TransitionSegment
from backend.app.domain.lighting import LightFrame

_MS_PER_SECOND = 1000


def frame_duration_ms(fps: int) -> int:
    """Duracion nominal de un fotograma. Siempre >= 1 ms porque `fps <= 60`."""
    return round(_MS_PER_SECOND / fps)


def frame_count(duration_ms: int, fps: int) -> int:
    """Cuantos fotogramas ocupa una transicion. Nunca cero: un segmento se ve."""
    return max(1, round(duration_ms / _MS_PER_SECOND * fps))


def render_segments(
    segments: Iterable[Segment],
    *,
    fps: int,
    color_space: ColorSpace = ColorSpace.HSV,
) -> Iterator[LightFrame]:
    """Convierte una secuencia de segmentos en fotogramas, sin materializarla.

    Perezoso a proposito: un efecto en bucle es una secuencia infinita y
    construir la lista colgaria el proceso.
    """
    nominal_ms = frame_duration_ms(fps)
    first = True

    for segment in segments:
        match segment:
            case HoldSegment():
                # Un unico fotograma: su duracion es la del hold, no la nominal.
                # Un STATIC no debe gastar una escritura BLE cada 50 ms.
                yield LightFrame(
                    color=segment.color,
                    brightness=segment.brightness,
                    duration_ms=max(1, segment.duration_ms),
                )
            case TransitionSegment():
                yield from _transition_frames(
                    segment,
                    fps=fps,
                    nominal_ms=nominal_ms,
                    color_space=color_space,
                    include_start=first,
                )
        first = False


def _transition_frames(
    segment: TransitionSegment,
    *,
    fps: int,
    nominal_ms: int,
    color_space: ColorSpace,
    include_start: bool,
) -> Iterator[LightFrame]:
    """Fotogramas de una transicion.

    `include_start` es False para todo segmento que no sea el primero de la
    secuencia: su origen ya se emitio como destino del anterior.
    """
    count = frame_count(segment.duration_ms, fps)
    if count == 1:
        # Sin sitio para interpolar: se emite el destino. Nunca el origen, que
        # ademas seria un fotograma repetido al encadenar.
        yield _frame_at(segment, 1.0, nominal_ms, color_space)
        return

    for index in range(0 if include_start else 1, count):
        yield _frame_at(segment, index / (count - 1), nominal_ms, color_space)


def _frame_at(
    segment: TransitionSegment,
    t: float,
    nominal_ms: int,
    color_space: ColorSpace,
) -> LightFrame:
    """El easing deforma el tiempo ANTES de interpolar, para color y brillo a la vez.

    Aplicarlo solo al color dejaria el brillo adelantandose al matiz en un
    `EASE_IN_OUT`, que es justo lo que hace que un `PULSE` parezca mecanico.
    """
    eased = ease(segment.easing, t)
    return LightFrame(
        color=interpolate_color(segment.start, segment.end, eased, space=color_space),
        brightness=interpolate_brightness(segment.start_brightness, segment.end_brightness, eased),
        duration_ms=nominal_ms,
    )
