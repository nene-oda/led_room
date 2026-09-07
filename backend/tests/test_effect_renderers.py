"""Los cuatro renderers: que segmentos produce cada algoritmo.

Se prueban los **segmentos** y no los fotogramas: la aritmetica de fps ya tiene
su propio modulo de test, y probarla otra vez aqui la duplicaria justo donde el
diseño la centraliza.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from backend.app.domain.devices.models import SINGLE_COLOR_STRIP
from backend.app.domain.effects.engine import EffectPlan, build_plan, segment_stream
from backend.app.domain.effects.models import (
    EffectDefinition,
    EffectStep,
    EffectType,
)
from backend.app.domain.effects.segments import HoldSegment, TransitionSegment
from backend.app.domain.lighting import RGBColor

AZUL = RGBColor.from_hex("#009DFF")
MORADO = RGBColor.from_hex("#7B00FF")
ROSA = RGBColor.from_hex("#FF008C")
PALETA = (AZUL, MORADO, ROSA)


def _plan(
    effect_type: EffectType,
    colores: tuple[RGBColor, ...],
    *,
    loop: bool = False,
    **kwargs: object,
) -> EffectPlan:
    definicion = EffectDefinition(
        id=uuid4(),
        name="Prueba",
        type=effect_type,
        loop=loop,
        steps=tuple(EffectStep(position=index, color=color) for index, color in enumerate(colores)),
        **kwargs,
    )
    return build_plan(definicion, capabilities=SINGLE_COLOR_STRIP, max_fps=20)


def _transiciones(plan: EffectPlan) -> list[TransitionSegment]:
    """Los segmentos del ciclo, comprobando de paso que todos son transiciones.

    Sin esta comprobacion, un renderer que devolviera un `HoldSegment` por error
    pasaria los asertos de color: la union tiene dos miembros y solo uno de ellos
    tiene `start` y `end`.
    """
    segmentos = list(plan.cycle())
    assert all(isinstance(segmento, TransitionSegment) for segmento in segmentos)
    return [segmento for segmento in segmentos if isinstance(segmento, TransitionSegment)]


def test_estatico_produce_un_unico_hold() -> None:
    segmentos = list(_plan(EffectType.STATIC, (AZUL,)).cycle())

    assert len(segmentos) == 1
    assert isinstance(segmentos[0], HoldSegment)
    assert segmentos[0].color == AZUL


def test_ciclo_suave_sin_bucle_encadena_los_colores_sin_volver_al_primero() -> None:
    segmentos = _transiciones(_plan(EffectType.SMOOTH_CYCLE, PALETA))

    assert len(segmentos) == 2
    assert [(s.start, s.end) for s in segmentos] == [(AZUL, MORADO), (MORADO, ROSA)]


def test_ciclo_suave_con_bucle_cierra_el_circulo() -> None:
    segmentos = _transiciones(_plan(EffectType.SMOOTH_CYCLE, PALETA, loop=True))

    assert len(segmentos) == 3
    assert (segmentos[-1].start, segmentos[-1].end) == (ROSA, AZUL)


def test_pulso_baja_y_sube_el_brillo_sin_cambiar_de_color() -> None:
    plan = _plan(EffectType.PULSE, (AZUL,), min_brightness=20, max_brightness=90)
    segmentos = _transiciones(plan)

    assert len(segmentos) == 2
    assert {s.start for s in segmentos} == {AZUL}
    assert {s.end for s in segmentos} == {AZUL}
    assert (segmentos[0].start_brightness, segmentos[0].end_brightness) == (90, 20)
    assert (segmentos[1].start_brightness, segmentos[1].end_brightness) == (20, 90)


def test_respiracion_cambia_de_color_con_la_luz_baja() -> None:
    """Es lo que evita que el cambio de color se vea como un corte."""
    plan = _plan(EffectType.BREATH, PALETA, loop=True, min_brightness=10)
    segmentos = _transiciones(plan)

    assert len(segmentos) == 6
    # Primer paso: se apaga sobre azul y vuelve a encenderse ya sobre morado.
    assert (segmentos[0].start, segmentos[0].end) == (AZUL, AZUL)
    assert segmentos[0].end_brightness == 10
    assert (segmentos[1].start, segmentos[1].end) == (AZUL, MORADO)
    assert segmentos[1].start_brightness == 10
    # Cierra el ciclo volviendo al primer color.
    assert (segmentos[-1].start, segmentos[-1].end) == (ROSA, AZUL)


def test_respiracion_de_un_solo_color_degenera_en_un_pulso() -> None:
    plan = _plan(EffectType.BREATH, (AZUL,), min_brightness=10)
    segmentos = _transiciones(plan)

    assert len(segmentos) == 2
    assert {s.start for s in segmentos} == {AZUL}


def test_respiracion_sin_bucle_termina_encendida_sobre_el_ultimo_color() -> None:
    """Acabar a media respiracion dejaria la tira apagada sin que nadie lo pidiera."""
    segmentos = _transiciones(_plan(EffectType.BREATH, PALETA, min_brightness=0))

    assert (segmentos[-1].start, segmentos[-1].end) == (ROSA, ROSA)
    assert segmentos[-1].end_brightness == 100


def test_el_suelo_nunca_supera_al_brillo_del_vertice() -> None:
    """Un suelo por encima del techo del paso daria un pulso que sube al apagarse.

    Es representable porque el suelo es del efecto y el techo, del paso: la
    definicion solo garantiza `min_brightness <= max_brightness`.
    """
    definicion = EffectDefinition(
        id=uuid4(),
        name="Pulso tenue",
        type=EffectType.PULSE,
        min_brightness=90,
        steps=(EffectStep(position=0, color=AZUL, brightness=40),),
    )
    plan = build_plan(definicion, capabilities=SINGLE_COLOR_STRIP, max_fps=20)

    segmentos = _transiciones(plan)

    assert segmentos[0].start_brightness == 40
    assert segmentos[0].end_brightness == 40


def test_un_efecto_en_bucle_produce_una_secuencia_infinita_de_segmentos() -> None:
    plan = _plan(EffectType.SMOOTH_CYCLE, PALETA, loop=True)

    tomados = [segmento for _, segmento in zip(range(10), segment_stream(plan), strict=False)]

    assert len(tomados) == 10


def test_un_efecto_sin_bucle_agota_su_ciclo() -> None:
    plan = _plan(EffectType.SMOOTH_CYCLE, PALETA)

    assert len(list(segment_stream(plan))) == 2


@pytest.mark.parametrize(
    ("effect_type", "colores"),
    [
        (EffectType.STATIC, (AZUL,)),
        (EffectType.SMOOTH_CYCLE, PALETA),
        (EffectType.PULSE, (AZUL,)),
        (EffectType.BREATH, PALETA),
    ],
)
def test_todo_renderer_produce_al_menos_un_segmento(
    effect_type: EffectType, colores: tuple[RGBColor, ...]
) -> None:
    assert list(_plan(effect_type, colores).cycle())
