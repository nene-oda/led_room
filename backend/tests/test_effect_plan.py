"""`build_plan`: autoridad de speed/transition_ms/fps, capacidades y precedencia.

Aqui se prueba la parte del motor que decide **cuanto dura** cada cosa y **si
se puede reproducir**. Ninguna de estas pruebas toca el reloj ni el dispositivo:
construir un plan no escribe nada, y eso es justamente lo que garantiza el
"cero `apply_frame`" cuando falta una capacidad.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.app.domain.devices.models import SINGLE_COLOR_STRIP, DeviceCapabilities
from backend.app.domain.devices.ports import DeviceCapabilityError
from backend.app.domain.effects.adaptation import adapt_frame, scale, supports
from backend.app.domain.effects.engine import build_plan, segment_stream, speed_factor
from backend.app.domain.effects.models import (
    Capability,
    Easing,
    EffectDefinition,
    EffectStep,
    EffectType,
)
from backend.app.domain.effects.registry import RENDERERS, renderer_for
from backend.app.domain.lighting import LightFrame, RGBColor

AZUL = RGBColor.from_hex("#009DFF")
MORADO = RGBColor.from_hex("#7B00FF")

SIN_RGB = DeviceCapabilities(
    rgb=False,
    brightness=True,
    effects=True,
    addressable=False,
    segments=False,
    white_channel=False,
    music_mode=False,
)
SIN_BRILLO = SIN_RGB.model_copy(update={"rgb": True, "brightness": False})


def _efecto(
    effect_type: EffectType = EffectType.SMOOTH_CYCLE,
    *,
    steps: tuple[EffectStep, ...] | None = None,
    **kwargs: object,
) -> EffectDefinition:
    if steps is None:
        steps = (
            EffectStep(position=0, color=AZUL),
            EffectStep(position=1, color=MORADO),
        )
    return EffectDefinition(
        id=kwargs.pop("id", uuid4()),
        name="Prueba",
        type=effect_type,
        steps=steps,
        **kwargs,
    )


def test_las_capacidades_del_motor_son_campos_reales_del_dispositivo() -> None:
    """`Capability` se resuelve con `getattr`: un nombre obsoleto reventaria en caliente."""
    assert {capability.value for capability in Capability} <= set(DeviceCapabilities.model_fields)


def test_todo_tipo_de_efecto_tiene_renderer() -> None:
    """Añadir un miembro a `EffectType` sin darlo de alta debe romper la build."""
    for effect_type in EffectType:
        assert renderer_for(effect_type) is RENDERERS[effect_type]


@pytest.mark.parametrize(
    ("speed", "factor"),
    [(0, 2.0), (50, 1.0), (100, 0.5)],
)
def test_la_velocidad_es_un_multiplicador_simetrico(speed: int, factor: float) -> None:
    assert speed_factor(speed) == pytest.approx(factor)


@pytest.mark.parametrize(
    ("speed", "esperado_ms"),
    [(0, 2000), (50, 1000), (100, 500)],
)
def test_la_velocidad_escala_la_duracion_base(speed: int, esperado_ms: int) -> None:
    plan = build_plan(
        _efecto(transition_ms=1000, speed=speed),
        capabilities=SINGLE_COLOR_STRIP,
        max_fps=20,
    )

    assert plan.steps[0].duration_ms == esperado_ms


def test_la_velocidad_de_la_escena_manda_sobre_la_del_efecto() -> None:
    """Precedencia congelada: `scene_target.speed` > `effect.speed`."""
    plan = build_plan(
        _efecto(transition_ms=1000, speed=0),
        capabilities=SINGLE_COLOR_STRIP,
        max_fps=20,
        speed=100,
    )

    assert plan.steps[0].duration_ms == 500


def test_los_fps_se_recortan_al_tope_del_despliegue() -> None:
    """Pedir 60 fps no puede inundar el enlace BLE."""
    plan = build_plan(_efecto(fps=60), capabilities=SINGLE_COLOR_STRIP, max_fps=20)

    assert plan.fps == 20


def test_un_efecto_mas_lento_que_el_tope_conserva_sus_fps() -> None:
    plan = build_plan(_efecto(fps=10), capabilities=SINGLE_COLOR_STRIP, max_fps=20)

    assert plan.fps == 10


@pytest.mark.parametrize("transition_ms", [0, 1])
def test_una_duracion_degenerada_sube_al_suelo_de_un_fotograma(transition_ms: int) -> None:
    """Sin suelo, la linea de tiempo avanzaria sin gastar tiempo."""
    plan = build_plan(
        _efecto(transition_ms=transition_ms),
        capabilities=SINGLE_COLOR_STRIP,
        max_fps=20,
    )

    assert plan.steps[0].duration_ms == 50
    assert plan.frame_duration_ms == 50


def test_la_duracion_por_paso_manda_sobre_la_del_efecto() -> None:
    """Es lo que hace que `CUSTOM` sea `SMOOTH_CYCLE` y no un tipo nuevo."""
    plan = build_plan(
        _efecto(
            transition_ms=1000,
            steps=(
                EffectStep(position=0, color=AZUL, duration_ms=4000),
                EffectStep(position=1, color=MORADO),
            ),
        ),
        capabilities=SINGLE_COLOR_STRIP,
        max_fps=20,
    )

    assert [step.duration_ms for step in plan.steps] == [4000, 1000]


def test_el_brillo_de_la_escena_manda_sobre_el_del_paso_y_este_sobre_el_base() -> None:
    definicion = _efecto(
        max_brightness=80,
        steps=(
            EffectStep(position=0, color=AZUL, brightness=30),
            EffectStep(position=1, color=MORADO),
        ),
    )

    sin_anulacion = build_plan(definicion, capabilities=SINGLE_COLOR_STRIP, max_fps=20)
    con_anulacion = build_plan(
        definicion, capabilities=SINGLE_COLOR_STRIP, max_fps=20, brightness=55
    )

    assert [step.brightness for step in sin_anulacion.steps] == [30, 80]
    assert [step.brightness for step in con_anulacion.steps] == [55, 55]


@pytest.mark.parametrize("brillo", [0, 100])
def test_los_brillos_extremos_son_validos(brillo: int) -> None:
    plan = build_plan(
        _efecto(
            steps=(
                EffectStep(position=0, color=AZUL, brightness=brillo),
                EffectStep(position=1, color=MORADO, brightness=brillo),
            )
        ),
        capabilities=SINGLE_COLOR_STRIP,
        max_fps=20,
    )

    assert [step.brightness for step in plan.steps] == [brillo, brillo]


def test_cada_algoritmo_impone_su_curva_por_defecto() -> None:
    """Un `PULSE` lineal parece mecanico; el renderer decide, no el constructor."""
    pulso = build_plan(
        _efecto(EffectType.PULSE, steps=(EffectStep(position=0, color=AZUL),)),
        capabilities=SINGLE_COLOR_STRIP,
        max_fps=20,
    )
    ciclo = build_plan(_efecto(), capabilities=SINGLE_COLOR_STRIP, max_fps=20)

    assert pulso.steps[0].easing is Easing.EASE_IN_OUT
    assert ciclo.steps[0].easing is Easing.LINEAR


def test_un_easing_explicito_en_el_paso_gana_al_del_algoritmo() -> None:
    plan = build_plan(
        _efecto(
            EffectType.PULSE,
            steps=(EffectStep(position=0, color=AZUL, easing=Easing.LINEAR),),
        ),
        capabilities=SINGLE_COLOR_STRIP,
        max_fps=20,
    )

    assert plan.steps[0].easing is Easing.LINEAR


def test_sin_capacidad_rgb_el_plan_se_rechaza_nombrando_la_que_falta() -> None:
    """Requisito duro -> 409 antes de la primera escritura (NEXT_STEPS 6.8)."""
    with pytest.raises(DeviceCapabilityError) as error:
        build_plan(_efecto(), capabilities=SIN_RGB, max_fps=20)

    assert "rgb" in str(error.value)


def test_sin_capacidad_de_brillo_el_plan_se_construye_igual() -> None:
    """El brillo es un requisito **blando**: se degrada en el borde, no se rechaza."""
    plan = build_plan(_efecto(), capabilities=SIN_BRILLO, max_fps=20)

    assert plan.steps


def test_un_ciclo_suave_de_un_solo_color_se_rechaza() -> None:
    with pytest.raises(ValueError, match="al menos 2"):
        build_plan(
            _efecto(steps=(EffectStep(position=0, color=AZUL),)),
            capabilities=SINGLE_COLOR_STRIP,
            max_fps=20,
        )


def test_un_estatico_de_dos_colores_se_rechaza() -> None:
    with pytest.raises(ValueError, match="como mucho 1"):
        build_plan(_efecto(EffectType.STATIC), capabilities=SINGLE_COLOR_STRIP, max_fps=20)


def test_un_estatico_no_entra_en_bucle_aunque_lo_pida() -> None:
    """Repetir un color fijo solo gastaria escrituras."""
    plan = build_plan(
        _efecto(EffectType.STATIC, loop=True, steps=(EffectStep(position=0, color=AZUL),)),
        capabilities=SINGLE_COLOR_STRIP,
        max_fps=20,
    )

    assert plan.loop is False
    assert len(list(segment_stream(plan))) == 1


def test_una_envolvente_invertida_se_rechaza_al_definir_el_efecto() -> None:
    with pytest.raises(ValueError, match="min_brightness"):
        _efecto(min_brightness=80, max_brightness=20)


def test_las_posiciones_repetidas_se_rechazan_al_definir_el_efecto() -> None:
    with pytest.raises(ValueError, match="unicas"):
        _efecto(
            steps=(
                EffectStep(position=0, color=AZUL),
                EffectStep(position=0, color=MORADO),
            )
        )


def test_el_plan_conserva_el_identificador_del_efecto() -> None:
    identificador = UUID("11111111-2222-3333-4444-555555555555")

    plan = build_plan(_efecto(id=identificador), capabilities=SINGLE_COLOR_STRIP, max_fps=20)

    assert plan.effect_id == identificador


def test_sin_control_de_brillo_el_brillo_se_pliega_sobre_el_color() -> None:
    """Requisito blando degradado en el borde de renderizado."""
    frame = LightFrame(color=RGBColor(r=200, g=100, b=50), brightness=50, duration_ms=50)

    adaptado = adapt_frame(frame, SIN_BRILLO)

    assert adaptado.color == RGBColor(r=100, g=50, b=25)
    assert adaptado.brightness == 100
    assert adaptado.duration_ms == 50


def test_con_control_de_brillo_el_fotograma_no_se_toca() -> None:
    frame = LightFrame(color=RGBColor(r=200, g=100, b=50), brightness=50, duration_ms=50)

    assert adapt_frame(frame, SINGLE_COLOR_STRIP) is frame


@pytest.mark.parametrize(
    ("brillo", "esperado"),
    [(0, RGBColor(r=0, g=0, b=0)), (100, RGBColor(r=255, g=128, b=0))],
)
def test_plegar_el_brillo_respeta_los_extremos(brillo: int, esperado: RGBColor) -> None:
    assert scale(RGBColor(r=255, g=128, b=0), brillo) == esperado


def test_la_consulta_de_capacidades_lee_el_campo_del_dominio() -> None:
    assert supports(SINGLE_COLOR_STRIP, Capability.RGB) is True
    assert supports(SIN_BRILLO, Capability.BRIGHTNESS) is False
