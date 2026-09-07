"""La unica regla de negocio de un perfil: cual es su escena predeterminada.

Se prueba aqui, sobre el modelo puro, porque tiene que dar el mismo resultado
tambien con datos contradictorios -- dos escenas marcadas, ninguna, o dos en la
misma posicion -- y eso no depende ni de la base ni del dispositivo.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain.profiles.models import Profile, ProfileScene

# Ordenados a proposito: A < B < C como UUID, que es el ultimo criterio de
# desempate. Escribirlos literales es lo que hace observable ese criterio.
ESCENA_A = UUID("aaaaaaaa-0000-0000-0000-000000000000")
ESCENA_B = UUID("bbbbbbbb-0000-0000-0000-000000000000")
ESCENA_C = UUID("cccccccc-0000-0000-0000-000000000000")


def _perfil(*scenes: ProfileScene, nombre: str = "Gaming") -> Profile:
    return Profile(id=uuid4(), name=nombre, scenes=scenes)


def test_un_perfil_sin_escenas_no_tiene_escena_predeterminada() -> None:
    assert _perfil().default_scene_id() is None


def test_manda_la_escena_marcada_como_predeterminada() -> None:
    perfil = _perfil(
        ProfileScene(scene_id=ESCENA_A, position=0),
        ProfileScene(scene_id=ESCENA_B, position=1, is_default=True),
    )

    assert perfil.default_scene_id() == ESCENA_B


def test_sin_ninguna_marcada_gana_la_de_menor_posicion() -> None:
    perfil = _perfil(
        ProfileScene(scene_id=ESCENA_C, position=5),
        ProfileScene(scene_id=ESCENA_A, position=2),
    )

    assert perfil.default_scene_id() == ESCENA_A


def test_con_varias_marcadas_gana_la_de_menor_posicion() -> None:
    perfil = _perfil(
        ProfileScene(scene_id=ESCENA_C, position=7, is_default=True),
        ProfileScene(scene_id=ESCENA_B, position=3, is_default=True),
        # Sin marcar y en la posicion 0: no puede ganar a una marcada.
        ProfileScene(scene_id=ESCENA_A, position=0),
    )

    assert perfil.default_scene_id() == ESCENA_B


def test_dos_escenas_en_la_misma_posicion_se_desempatan_por_identificador() -> None:
    """Sin este criterio, el mismo boton activaria una u otra segun el orden de las filas."""
    perfil = _perfil(
        ProfileScene(scene_id=ESCENA_C, position=1),
        ProfileScene(scene_id=ESCENA_A, position=1),
        ProfileScene(scene_id=ESCENA_B, position=1),
    )

    assert perfil.default_scene_id() == ESCENA_A


def test_el_desempate_no_depende_del_orden_en_que_llegan_las_escenas() -> None:
    enlaces = (
        ProfileScene(scene_id=ESCENA_A, position=1),
        ProfileScene(scene_id=ESCENA_B, position=1),
        ProfileScene(scene_id=ESCENA_C, position=1),
    )

    directo = _perfil(*enlaces).default_scene_id()
    invertido = _perfil(*reversed(enlaces)).default_scene_id()

    assert directo == invertido == ESCENA_A


def test_un_perfil_no_puede_contener_dos_veces_la_misma_escena() -> None:
    """La clave primaria de `profile_scenes` es (profile_id, scene_id)."""
    with pytest.raises(ValidationError, match="dos veces la misma escena"):
        _perfil(
            ProfileScene(scene_id=ESCENA_A, position=0),
            ProfileScene(scene_id=ESCENA_A, position=1),
        )


def test_una_posicion_negativa_no_es_un_orden() -> None:
    with pytest.raises(ValidationError):
        ProfileScene(scene_id=ESCENA_A, position=-1)
