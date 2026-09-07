"""Generacion de fotogramas: la formula congelada y el vertice unico.

Es el unico sitio del proyecto con aritmetica de fps, asi que es el unico sitio
donde hay que probarla.
"""

from __future__ import annotations

import pytest

from backend.app.domain.effects.frames import (
    frame_count,
    frame_duration_ms,
    render_segments,
)
from backend.app.domain.effects.models import ColorSpace, Easing
from backend.app.domain.effects.segments import HoldSegment, TransitionSegment
from backend.app.domain.lighting import RGBColor

AZUL = RGBColor.from_hex("#003CFF")
MORADO = RGBColor.from_hex("#7B00FF")
ROSA = RGBColor.from_hex("#FF008C")


def _transicion(
    start: RGBColor,
    end: RGBColor,
    duration_ms: int,
    *,
    brillo: tuple[int, int] = (100, 100),
) -> TransitionSegment:
    return TransitionSegment(
        start=start,
        end=end,
        start_brightness=brillo[0],
        end_brightness=brillo[1],
        duration_ms=duration_ms,
        easing=Easing.LINEAR,
    )


def test_el_ejemplo_del_readme_da_ochenta_fotogramas_de_cincuenta_milisegundos() -> None:
    """`transition_ms = 4000`, `fps = 20` -> 80 fotogramas de 50 ms (README 12)."""
    assert frame_duration_ms(20) == 50
    assert frame_count(4000, 20) == 80

    frames = list(render_segments([_transicion(AZUL, MORADO, 4000)], fps=20))

    assert len(frames) == 80
    assert {frame.duration_ms for frame in frames} == {50}


def test_los_extremos_de_una_transicion_son_exactos() -> None:
    frames = list(render_segments([_transicion(AZUL, MORADO, 1000)], fps=20))

    assert frames[0].color == AZUL
    assert frames[-1].color == MORADO


@pytest.mark.parametrize("duration_ms", [0, 1, 24])
def test_una_transicion_mas_corta_que_un_fotograma_emite_solo_el_destino(
    duration_ms: int,
) -> None:
    """`frames == 1` -> `t = 1.0`. Emitir el origen dejaria la luz sin llegar."""
    assert frame_count(duration_ms, 20) == 1

    frames = list(render_segments([_transicion(AZUL, MORADO, duration_ms)], fps=20))

    assert len(frames) == 1
    assert frames[0].color == MORADO


def test_el_vertice_entre_dos_segmentos_se_emite_una_sola_vez() -> None:
    """Emitirlo dos veces produce un micro-tartamudeo en cada vertice."""
    frames = list(
        render_segments(
            [_transicion(AZUL, MORADO, 1000), _transicion(MORADO, ROSA, 1000)],
            fps=20,
        )
    )

    # 20 + 19: el primer fotograma del segundo segmento ya se emitio como
    # ultimo del primero.
    assert len(frames) == 39
    assert frames[19].color == MORADO
    assert frames[20].color != MORADO
    assert frames[-1].color == ROSA


def test_la_vuelta_del_bucle_tampoco_repite_el_vertice() -> None:
    """Un ciclo cerrado A->B->A encadenado consigo mismo no puede tartamudear."""
    ciclo = [_transicion(AZUL, MORADO, 1000), _transicion(MORADO, AZUL, 1000)]

    frames = list(render_segments(ciclo + ciclo, fps=20))

    # 20 + 19 + 19 + 19: solo el primerisimo fotograma incluye su origen.
    assert len(frames) == 77
    assert frames[38].color == AZUL
    assert frames[39].color != AZUL


def test_un_hold_produce_un_unico_fotograma_con_toda_su_duracion() -> None:
    """Un STATIC no debe gastar una escritura BLE cada 50 ms."""
    frames = list(
        render_segments(
            [HoldSegment(color=AZUL, brightness=60, duration_ms=5000)],
            fps=20,
        )
    )

    assert len(frames) == 1
    assert frames[0].duration_ms == 5000
    assert frames[0].brightness == 60


def test_un_hold_de_duracion_cero_sigue_produciendo_un_fotograma_valido() -> None:
    """`LightFrame.duration_ms` es `> 0`: un 0 crudo reventaria la validacion."""
    frames = list(render_segments([HoldSegment(color=AZUL, brightness=0, duration_ms=0)], fps=20))

    assert frames[0].duration_ms == 1


def test_el_brillo_se_interpola_junto_al_color() -> None:
    frames = list(render_segments([_transicion(AZUL, MORADO, 1000, brillo=(0, 100))], fps=20))

    assert frames[0].brightness == 0
    assert frames[-1].brightness == 100
    assert frames[9].brightness == pytest.approx(47, abs=1)


def test_el_generador_es_perezoso_y_admite_una_secuencia_infinita() -> None:
    """Un efecto en bucle es infinito: materializarlo colgaria el proceso."""

    def infinita() -> object:
        while True:
            yield _transicion(AZUL, MORADO, 1000)

    frames = render_segments(infinita(), fps=20)  # type: ignore[arg-type]

    assert sum(1 for _, _ in zip(range(100), frames, strict=False)) == 100


@pytest.mark.parametrize(
    ("fps", "esperado_ms"),
    [(1, 1000), (10, 100), (20, 50), (60, 17)],
)
def test_la_duracion_de_un_fotograma_sale_de_los_fps(fps: int, esperado_ms: int) -> None:
    assert frame_duration_ms(fps) == esperado_ms


def test_el_espacio_de_color_llega_hasta_el_fotograma() -> None:
    """El parametro no es decorativo: cambia el color que se aplica."""
    hsv = list(render_segments([_transicion(AZUL, ROSA, 1000)], fps=20, color_space=ColorSpace.HSV))
    rgb = list(render_segments([_transicion(AZUL, ROSA, 1000)], fps=20, color_space=ColorSpace.RGB))

    assert hsv[10].color != rgb[10].color
