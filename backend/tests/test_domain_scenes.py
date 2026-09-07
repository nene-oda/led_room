"""Invariantes del modelo de dominio de escenas.

Lo que se prueba aqui son las reglas que hacen irrepresentable una escena
incoherente. Nada de esto necesita base de datos ni dispositivo: si hiciera
falta uno de los dos, la regla estaria en la capa equivocada.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain.scenes.models import NAME_MAX_LENGTH, Scene, SceneTarget

SALON = UUID("11111111-1111-1111-1111-111111111111")
DORMITORIO = UUID("22222222-2222-2222-2222-222222222222")
EFECTO = UUID("33333333-3333-3333-3333-333333333333")


def _escena(*targets: SceneTarget, nombre: str = "Noche") -> Scene:
    return Scene(id=uuid4(), name=nombre, targets=targets)


def test_un_objetivo_sin_anulaciones_hereda_lo_del_efecto() -> None:
    """`None` significa "usa lo del efecto", nunca "usa cero"."""
    objetivo = SceneTarget(device_id=SALON, effect_id=EFECTO)

    assert (objetivo.brightness, objetivo.speed) == (None, None)
    assert objetivo.enabled is True


def test_una_escena_no_puede_tener_dos_objetivos_para_el_mismo_dispositivo() -> None:
    """El segundo pisaria al primero sobre la misma tira (UNIQUE de la tabla)."""
    with pytest.raises(ValidationError, match="dos objetivos para el mismo dispositivo"):
        _escena(
            SceneTarget(device_id=SALON, effect_id=EFECTO),
            SceneTarget(device_id=SALON, effect_id=uuid4()),
        )


def test_los_objetivos_deshabilitados_no_entran_en_la_activacion() -> None:
    escena = _escena(
        SceneTarget(device_id=SALON, effect_id=EFECTO),
        SceneTarget(device_id=DORMITORIO, effect_id=EFECTO, enabled=False),
    )

    assert [objetivo.device_id for objetivo in escena.enabled_targets] == [SALON]
    assert len(escena.targets) == 2


def test_un_nombre_vacio_no_es_una_escena() -> None:
    with pytest.raises(ValidationError):
        Scene(id=uuid4(), name="")


def test_una_copia_estrena_identidad_y_conserva_los_objetivos() -> None:
    original = _escena(SceneTarget(device_id=SALON, effect_id=EFECTO, brightness=10))
    nuevo = uuid4()

    copia = original.duplicated(nuevo)

    assert copia.id == nuevo
    assert copia.name == "Noche (copia)"
    assert copia.targets == original.targets


def test_la_copia_de_una_escena_de_fabrica_ya_no_lo_es() -> None:
    """Si lo siguiera siendo, la UI no dejaria borrar algo que creo el usuario."""
    original = Scene(id=uuid4(), name="Noche", is_builtin=True)

    assert original.duplicated(uuid4()).is_builtin is False


def test_una_copia_puede_llevar_el_nombre_que_pida_el_cliente() -> None:
    original = _escena()

    assert original.duplicated(uuid4(), name="Noche v2").name == "Noche v2"


def test_el_nombre_de_una_copia_nunca_desborda_la_longitud_maxima() -> None:
    """Duplicar una escena ya larga no puede fallar con un 422 del propio servidor."""
    original = _escena(nombre="N" * NAME_MAX_LENGTH)

    copia = original.duplicated(uuid4())

    assert len(copia.name) == NAME_MAX_LENGTH
