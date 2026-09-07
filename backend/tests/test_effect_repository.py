"""Mapper y repositorio de efectos contra SQLite real, en memoria.

Round-trip completo: lo que entra por el dominio tiene que volver identico, con
los pasos ordenados y sin que ningun enumerado se degrade a texto suelto.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from backend.app.domain.effects.models import (
    Easing,
    EffectDefinition,
    EffectStep,
    EffectType,
)
from backend.app.domain.lighting import RGBColor
from backend.app.infrastructure.persistence.database import (
    IN_MEMORY_URL,
    create_all,
    create_database_engine,
)
from backend.app.infrastructure.persistence.mappers.effect import (
    EffectMappingError,
    effect_to_domain,
)
from backend.app.infrastructure.persistence.models.effect import EffectRecord, EffectStepRecord
from backend.app.infrastructure.persistence.repositories import SQLModelEffectRepository

AZUL = RGBColor.from_hex("#009DFF")
MORADO = RGBColor.from_hex("#7B00FF")
ROSA = RGBColor.from_hex("#FF008C")


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = create_database_engine(url=IN_MEMORY_URL)
    create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def repository(engine: Engine) -> Iterator[SQLModelEffectRepository]:
    with Session(engine) as session:
        yield SQLModelEffectRepository(session)


def _cyberpunk() -> EffectDefinition:
    return EffectDefinition(
        id=uuid4(),
        name="Cyberpunk",
        type=EffectType.SMOOTH_CYCLE,
        description="Azul, morado y rosa",
        loop=True,
        speed=40,
        fps=15,
        transition_ms=3500,
        min_brightness=20,
        max_brightness=90,
        steps=(
            EffectStep(position=0, color=AZUL, easing=Easing.EASE_IN_OUT),
            EffectStep(position=1, color=MORADO, brightness=60, duration_ms=2000),
            EffectStep(position=2, color=ROSA),
        ),
    )


def test_un_efecto_completo_sobrevive_al_viaje_de_ida_y_vuelta(
    repository: SQLModelEffectRepository,
) -> None:
    efecto = _cyberpunk()

    repository.upsert(efecto)

    assert repository.get(efecto.id) == efecto


def test_los_colores_se_guardan_en_mayusculas(
    engine: Engine, repository: SQLModelEffectRepository
) -> None:
    """Una sola forma del color en la base (ARCHITECTURE 3.2)."""
    efecto = _cyberpunk()
    repository.upsert(efecto)

    with Session(engine) as session:
        record = session.get(EffectRecord, efecto.id)
        assert record is not None
        assert [step.color_hex for step in record.steps] == ["#009DFF", "#7B00FF", "#FF008C"]


def test_una_envolvente_por_defecto_se_guarda_como_cero_y_cien(
    repository: SQLModelEffectRepository,
) -> None:
    efecto = EffectDefinition(
        id=uuid4(),
        name="Simple",
        type=EffectType.STATIC,
        steps=(EffectStep(position=0, color=AZUL),),
    )

    guardado = repository.upsert(efecto)

    assert (guardado.min_brightness, guardado.max_brightness) == (0, 100)


def test_una_fila_sin_envolvente_hereda_la_del_dominio(engine: Engine) -> None:
    """`NULL` significa "usa la por defecto", no "usa cero"."""
    identificador = uuid4()
    with Session(engine) as session:
        session.add(
            EffectRecord(
                id=identificador,
                name="Antiguo",
                type=EffectType.STATIC.value,
                loop=False,
                speed=50,
                fps=20,
                transition_ms=1000,
                min_brightness=None,
                max_brightness=None,
            )
        )
        session.commit()
        record = session.get(EffectRecord, identificador)
        assert record is not None

        efecto = effect_to_domain(record)

    assert (efecto.min_brightness, efecto.max_brightness) == (0, 100)


def test_reemplazar_un_efecto_sustituye_sus_pasos(
    engine: Engine, repository: SQLModelEffectRepository
) -> None:
    """Los pasos son una secuencia posicional sin identidad propia."""
    efecto = _cyberpunk()
    repository.upsert(efecto)

    reducido = efecto.model_copy(
        update={"steps": (EffectStep(position=0, color=ROSA),), "type": EffectType.STATIC}
    )
    repository.upsert(reducido)

    releido = repository.get(efecto.id)
    assert releido is not None
    assert [step.color for step in releido.steps] == [ROSA]

    with Session(engine) as session:
        assert len(session.exec(select(EffectStepRecord)).all()) == 1


def test_reemplazar_conserva_el_identificador_y_los_pasos_no_quedan_huerfanos(
    repository: SQLModelEffectRepository,
) -> None:
    efecto = _cyberpunk()
    repository.upsert(efecto)

    renombrado = efecto.model_copy(update={"name": "Cyberpunk v2"})
    guardado = repository.upsert(renombrado)

    assert guardado.id == efecto.id
    assert guardado.name == "Cyberpunk v2"


def test_borrar_devuelve_si_habia_algo_que_borrar(
    repository: SQLModelEffectRepository,
) -> None:
    efecto = _cyberpunk()
    repository.upsert(efecto)

    assert repository.delete(efecto.id) is True
    assert repository.delete(efecto.id) is False
    assert repository.get(efecto.id) is None


def test_borrar_un_efecto_arrastra_sus_pasos(
    engine: Engine, repository: SQLModelEffectRepository
) -> None:
    efecto = _cyberpunk()
    repository.upsert(efecto)
    repository.delete(efecto.id)

    with Session(engine) as session:
        assert session.exec(select(EffectStepRecord)).all() == []


def test_el_catalogo_sale_ordenado_por_nombre(
    repository: SQLModelEffectRepository,
) -> None:
    for nombre in ("Zeta", "Alfa", "Media"):
        repository.upsert(_cyberpunk().model_copy(update={"id": uuid4(), "name": nombre}))

    assert [efecto.name for efecto in repository.list_all()] == ["Alfa", "Media", "Zeta"]


def test_un_tipo_desconocido_en_la_base_no_se_degrada_en_silencio(engine: Engine) -> None:
    """Una fila escrita a mano o por una version mas nueva no puede pasar callando."""
    identificador = uuid4()
    with Session(engine) as session:
        session.add(
            EffectRecord(
                id=identificador,
                name="Del futuro",
                type="TELETRANSPORTE",
                loop=False,
                speed=50,
                fps=20,
                transition_ms=1000,
            )
        )
        session.commit()
        record = session.get(EffectRecord, identificador)
        assert record is not None

        with pytest.raises(EffectMappingError, match="TELETRANSPORTE"):
            effect_to_domain(record)


def test_un_easing_desconocido_en_la_base_tampoco(engine: Engine) -> None:
    identificador = uuid4()
    with Session(engine) as session:
        session.add(
            EffectRecord(
                id=identificador,
                name="Raro",
                type=EffectType.STATIC.value,
                loop=False,
                speed=50,
                fps=20,
                transition_ms=1000,
            )
        )
        session.add(
            EffectStepRecord(
                effect_id=identificador,
                position=0,
                color_hex="#009DFF",
                easing="REBOTE",
            )
        )
        session.commit()
        record = session.get(EffectRecord, identificador)
        assert record is not None

        with pytest.raises(EffectMappingError, match="REBOTE"):
            effect_to_domain(record)


def test_un_error_de_mapeo_no_es_un_valueerror() -> None:
    """Una fila corrupta es un 500, no un 422: no la escribio el cliente."""
    assert not issubclass(EffectMappingError, ValueError)
