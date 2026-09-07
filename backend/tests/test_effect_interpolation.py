"""Interpolacion: extremos exactos, arco corto de matiz y el control negativo.

Todo lo de este modulo son funciones puras: ni reloj, ni tareas, ni hardware.
"""

from __future__ import annotations

import colorsys

import pytest

from backend.app.domain.effects.interpolators import (
    clamp01,
    ease,
    interpolate_brightness,
    interpolate_color,
    lerp,
)
from backend.app.domain.effects.models import ColorSpace, Easing
from backend.app.domain.lighting import RGBColor

AZUL = RGBColor.from_hex("#009DFF")
ROSA = RGBColor.from_hex("#FF008C")
NEGRO = RGBColor(r=0, g=0, b=0)
BLANCO = RGBColor(r=255, g=255, b=255)


def _saturacion(color: RGBColor) -> float:
    return colorsys.rgb_to_hsv(color.r / 255, color.g / 255, color.b / 255)[1]


@pytest.mark.parametrize("space", list(ColorSpace))
def test_en_t_cero_sale_exactamente_el_origen_y_en_t_uno_el_destino(space: ColorSpace) -> None:
    """El viaje RGB->HSV->RGB es de coma flotante: los extremos no se recalculan."""
    assert interpolate_color(AZUL, ROSA, 0.0, space=space) == AZUL
    assert interpolate_color(AZUL, ROSA, 1.0, space=space) == ROSA


@pytest.mark.parametrize("t", [-1.0, -0.0001, 1.0001, 42.0])
def test_un_parametro_fuera_de_rango_se_recorta_en_vez_de_extrapolar(t: float) -> None:
    esperado = AZUL if t < 0 else ROSA
    assert interpolate_color(AZUL, ROSA, t) == esperado
    assert clamp01(t) in (0.0, 1.0)


def test_en_hsv_el_punto_medio_de_azul_a_rosa_conserva_la_saturacion() -> None:
    """Control positivo del espacio elegido (ARCHITECTURE 8)."""
    medio = interpolate_color(AZUL, ROSA, 0.5, space=ColorSpace.HSV)

    assert _saturacion(medio) >= 0.95


def test_control_negativo_en_rgb_el_punto_medio_se_desatura() -> None:
    """La misma prueba en RGB **falla**, y por eso HSV es el valor por defecto.

    Se deja escrita como contraste: sin ella, "interpolamos en HSV" seria una
    afirmacion sin evidencia. En RGB el punto medio es un malva sucio con menos
    del 40 % de saturacion.
    """
    medio = interpolate_color(AZUL, ROSA, 0.5, space=ColorSpace.RGB)

    assert _saturacion(medio) < 0.95
    assert medio.to_hex() == "#804EC6"


def test_el_matiz_recorre_el_arco_corto() -> None:
    """De rojo (0) a magenta (300) se baja, no se sube pasando por verde."""
    rojo = RGBColor.from_hex("#FF0000")
    magenta = RGBColor.from_hex("#FF00FF")

    medio = interpolate_color(rojo, magenta, 0.5)
    matiz = colorsys.rgb_to_hsv(medio.r / 255, medio.g / 255, medio.b / 255)[0]

    # Arco corto: 0 -> 0.833 pasando por 0.917 (rosa), nunca por 0.4 (verde).
    assert matiz == pytest.approx(0.9167, abs=0.01)


def test_un_extremo_acromatico_hereda_el_matiz_del_otro() -> None:
    """Un fundido a negro no puede girar el matiz: el negro no tiene ninguno."""
    medio = interpolate_color(AZUL, NEGRO, 0.5)
    matiz_medio = colorsys.rgb_to_hsv(medio.r / 255, medio.g / 255, medio.b / 255)[0]
    matiz_azul = colorsys.rgb_to_hsv(AZUL.r / 255, AZUL.g / 255, AZUL.b / 255)[0]

    # Tolerancia de 0.005: a medio brillo el color cabe en menos niveles de
    # 8 bits y el matiz reconstruido se desvia por el redondeo del canal.
    assert matiz_medio == pytest.approx(matiz_azul, abs=0.005)


def test_entre_dos_acromaticos_se_interpola_en_rgb() -> None:
    """Negro a blanco: sin matiz que barrer, el gris medio es exacto."""
    assert interpolate_color(NEGRO, BLANCO, 0.5).to_hex() == "#808080"


@pytest.mark.parametrize("easing", list(Easing))
def test_toda_curva_de_easing_respeta_los_extremos(easing: Easing) -> None:
    """Si `f(0) != 0` o `f(1) != 1`, un efecto en bucle salta en cada vuelta."""
    assert ease(easing, 0.0) == 0.0
    assert ease(easing, 1.0) == 1.0


@pytest.mark.parametrize(
    ("easing", "esperado"),
    [
        (Easing.LINEAR, 0.5),
        (Easing.EASE_IN, 0.25),
        (Easing.EASE_OUT, 0.75),
        (Easing.EASE_IN_OUT, 0.5),
    ],
)
def test_cada_curva_deforma_el_tiempo_como_su_nombre_promete(
    easing: Easing, esperado: float
) -> None:
    assert ease(easing, 0.5) == pytest.approx(esperado)


def test_el_brillo_interpola_con_extremos_exactos_y_dentro_de_rango() -> None:
    assert interpolate_brightness(0, 100, 0.0) == 0
    assert interpolate_brightness(0, 100, 1.0) == 100
    assert interpolate_brightness(0, 100, 0.5) == 50
    assert interpolate_brightness(100, 0, 0.25) == 75


def test_los_canales_extremos_sobreviven_al_viaje_de_ida_y_vuelta() -> None:
    """0 y 255 son los bordes donde un redondeo mal puesto produce un 256."""
    for t in (0.1, 0.25, 0.5, 0.75, 0.9):
        color = interpolate_color(NEGRO, BLANCO, t)
        assert 0 <= color.r <= 255
        assert 0 <= color.g <= 255
        assert 0 <= color.b <= 255


def test_lerp_es_lineal() -> None:
    assert lerp(10.0, 20.0, 0.0) == 10.0
    assert lerp(10.0, 20.0, 1.0) == 20.0
    assert lerp(10.0, 20.0, 0.5) == 15.0
