"""Matematica de la interpolacion. **Funciones puras**, sin reloj ni estado.

Aqui no hay cancelacion, ni tareas, ni fps: solo "dado un `t` entre 0 y 1, que
color y que brillo tocan". Separarlo del bucle es lo que permite probar la
interpolacion sin dormir ni un milisegundo (NEXT_STEPS 6.9).

**Espacio de interpolacion: HSV con arco corto de matiz** (ARCHITECTURE 8,
NEXT_STEPS 6.3). El motivo es medible: `#009DFF -> #FF008C` interpolado en RGB
pasa por `#7F4E7F`, un malva sucio con ~38 % de saturacion; en HSV mantiene la
saturacion al 100 % y barre el matiz por el lado corto.

Dos reglas deterministas para el caso que HSV no sabe resolver:

* si **un** extremo es acromatico (`s == 0` o `v == 0`, tipico de un fundido a
  negro) su matiz es indefinido, asi que **hereda el del otro**;
* si **ambos** lo son, no hay matiz que barrer y se interpola en RGB, que para
  dos grises es exacto.

OkLab queda descartado por ahora: exige decodificar gamma y una matriz de
conversion, y la gamma del driver PWM del controlador es desconocida, asi que la
fidelidad extra no seria observable.
"""

from __future__ import annotations

import colorsys

from backend.app.domain.effects.models import ColorSpace, Easing
from backend.app.domain.lighting import BRIGHTNESS_MAX, BRIGHTNESS_MIN, RGBColor

#: Medio giro de matiz. Un salto mayor que esto se recorre por el otro lado.
_HALF_TURN = 0.5

_CHANNEL_MAX = 255.0


def clamp01(value: float) -> float:
    """Recorta a [0, 1]. Es la unica puerta de entrada del parametro temporal."""
    return min(1.0, max(0.0, value))


def lerp(start: float, end: float, t: float) -> float:
    """Interpolacion lineal. `t` se asume ya recortado."""
    return start + (end - start) * t


def ease(easing: Easing, t: float) -> float:
    """Deforma el tiempo sin cambiar los extremos.

    Toda curva cumple `f(0) == 0` y `f(1) == 1`: si no, un efecto en bucle daria
    un salto en cada vuelta.
    """
    t = clamp01(t)
    match easing:
        case Easing.LINEAR:
            return t
        case Easing.EASE_IN:
            return t * t
        case Easing.EASE_OUT:
            return 1.0 - (1.0 - t) ** 2
        case Easing.EASE_IN_OUT:
            return 2.0 * t * t if t < 0.5 else 1.0 - 2.0 * (1.0 - t) ** 2


def interpolate_brightness(start: int, end: int, t: float) -> int:
    """Brillo entero 0-100 en el instante `t`, con los extremos exactos."""
    t = clamp01(t)
    if t <= 0.0:
        return start
    if t >= 1.0:
        return end
    return min(BRIGHTNESS_MAX, max(BRIGHTNESS_MIN, round(lerp(start, end, t))))


def interpolate_color(
    start: RGBColor,
    end: RGBColor,
    t: float,
    *,
    space: ColorSpace = ColorSpace.HSV,
) -> RGBColor:
    """Color en el instante `t`, con los extremos **exactos**.

    Los extremos se devuelven tal cual y no se recalculan: el viaje
    RGB -> HSV -> RGB es de coma flotante y podria desviarse un nivel, lo que
    haria que `t=1` no diera exactamente el color que el usuario eligio.
    """
    t = clamp01(t)
    if t <= 0.0:
        return start
    if t >= 1.0:
        return end
    if space is ColorSpace.RGB:
        return _mix_rgb(start, end, t)
    return _mix_hsv(start, end, t)


def _mix_rgb(start: RGBColor, end: RGBColor, t: float) -> RGBColor:
    return RGBColor(
        r=_channel(lerp(start.r, end.r, t)),
        g=_channel(lerp(start.g, end.g, t)),
        b=_channel(lerp(start.b, end.b, t)),
    )


def _mix_hsv(start: RGBColor, end: RGBColor, t: float) -> RGBColor:
    start_h, start_s, start_v = _to_hsv(start)
    end_h, end_s, end_v = _to_hsv(end)

    start_grey = _is_achromatic(start_s, start_v)
    end_grey = _is_achromatic(end_s, end_v)
    if start_grey and end_grey:
        # Ningun matiz que barrer: en RGB dos grises se interpolan exactos.
        return _mix_rgb(start, end, t)
    if start_grey:
        start_h = end_h
    elif end_grey:
        end_h = start_h

    hue = (start_h + _short_arc(start_h, end_h) * t) % 1.0
    red, green, blue = colorsys.hsv_to_rgb(
        hue,
        lerp(start_s, end_s, t),
        lerp(start_v, end_v, t),
    )
    return RGBColor(
        r=_channel(red * _CHANNEL_MAX),
        g=_channel(green * _CHANNEL_MAX),
        b=_channel(blue * _CHANNEL_MAX),
    )


def _short_arc(start_hue: float, end_hue: float) -> float:
    """Diferencia de matiz por el lado corto del circulo, en [-0.5, 0.5]."""
    delta = end_hue - start_hue
    if delta > _HALF_TURN:
        return delta - 1.0
    if delta < -_HALF_TURN:
        return delta + 1.0
    return delta


def _is_achromatic(saturation: float, value: float) -> bool:
    """Un gris o un negro: su matiz es indefinido y no se puede barrer."""
    return saturation == 0.0 or value == 0.0


def _to_hsv(color: RGBColor) -> tuple[float, float, float]:
    return colorsys.rgb_to_hsv(
        color.r / _CHANNEL_MAX,
        color.g / _CHANNEL_MAX,
        color.b / _CHANNEL_MAX,
    )


def _channel(value: float) -> int:
    """Redondea y recorta un canal a 0-255.

    El recorte no es defensivo por gusto: `hsv_to_rgb` puede devolver 1.0000001
    y `RGBColor` rechazaria un 256 con un `ValidationError` a mitad de un efecto.
    """
    return min(255, max(0, round(value)))
