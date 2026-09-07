"""Mapper y repositorio de perfiles contra SQLite real, en memoria.

Lo especifico de esta tabla: el enlace `profile_scenes` tiene clave primaria
compuesta y atributos propios (`position`, `is_default`), asi que reemplazar las
escenas de un perfil es la misma operacion delicada que reemplazar los objetivos
de una escena.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from backend.app.domain.profiles.models import Profile, ProfileScene
from backend.app.domain.scenes.models import Scene
from backend.app.infrastructure.persistence.database import (
    IN_MEMORY_URL,
    create_all,
    create_database_engine,
)
from backend.app.infrastructure.persistence.models.profile import ProfileSceneRecord
from backend.app.infrastructure.persistence.repositories import (
    SQLModelProfileRepository,
    SQLModelSceneRepository,
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = create_database_engine(url=IN_MEMORY_URL)
    create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture
def repository(session: Session) -> SQLModelProfileRepository:
    return SQLModelProfileRepository(session)


@pytest.fixture
def scenes(session: Session) -> SQLModelSceneRepository:
    return SQLModelSceneRepository(session)


def _escena(repository: SQLModelSceneRepository, nombre: str) -> UUID:
    """Una escena sin objetivos: el perfil solo necesita que exista."""
    return repository.upsert(Scene(id=uuid4(), name=nombre)).id


def test_un_perfil_completo_sobrevive_al_viaje_de_ida_y_vuelta(
    repository: SQLModelProfileRepository, scenes: SQLModelSceneRepository
) -> None:
    perfil = Profile(
        id=uuid4(),
        name="Gaming",
        description="Cyan y magenta",
        icon="gamepad",
        scenes=(
            ProfileScene(scene_id=_escena(scenes, "Cyberpunk"), position=0, is_default=True),
            ProfileScene(scene_id=_escena(scenes, "Purple pulse"), position=1),
        ),
    )

    repository.upsert(perfil)

    assert repository.get(perfil.id) == perfil


def test_las_escenas_se_leen_ordenadas_por_posicion(
    repository: SQLModelProfileRepository, scenes: SQLModelSceneRepository
) -> None:
    primera = _escena(scenes, "Primera")
    segunda = _escena(scenes, "Segunda")
    perfil = Profile(
        id=uuid4(),
        name="Relax",
        scenes=(
            ProfileScene(scene_id=segunda, position=1),
            ProfileScene(scene_id=primera, position=0),
        ),
    )

    guardado = repository.upsert(perfil)

    assert [link.scene_id for link in guardado.scenes] == [primera, segunda]


def test_guardar_dos_veces_reemplaza_las_escenas_del_perfil(
    session: Session,
    repository: SQLModelProfileRepository,
    scenes: SQLModelSceneRepository,
) -> None:
    """La clave primaria compuesta exige que los DELETE precedan a los INSERT."""
    primera = _escena(scenes, "Primera")
    segunda = _escena(scenes, "Segunda")
    perfil = Profile(id=uuid4(), name="Work", scenes=(ProfileScene(scene_id=primera),))
    repository.upsert(perfil)

    reemplazado = perfil.model_copy(
        update={"scenes": (ProfileScene(scene_id=segunda, is_default=True),)}
    )
    guardado = repository.upsert(reemplazado)

    assert [link.scene_id for link in guardado.scenes] == [segunda]
    assert len(session.exec(select(ProfileSceneRecord)).all()) == 1


def test_borrar_un_perfil_no_borra_sus_escenas(
    repository: SQLModelProfileRepository, scenes: SQLModelSceneRepository
) -> None:
    escena = _escena(scenes, "Compartida")
    perfil = Profile(id=uuid4(), name="Sleep", scenes=(ProfileScene(scene_id=escena),))
    repository.upsert(perfil)

    assert repository.delete(perfil.id) is True
    assert repository.get(perfil.id) is None
    assert scenes.get(escena) is not None


def test_borrar_una_escena_la_saca_de_los_perfiles_que_la_usaban(
    repository: SQLModelProfileRepository, scenes: SQLModelSceneRepository
) -> None:
    """CASCADE de `profile_scenes`: el perfil sigue existiendo, sin ese enlace."""
    escena = _escena(scenes, "Efimera")
    otra = _escena(scenes, "Duradera")
    perfil = Profile(
        id=uuid4(),
        name="Party",
        scenes=(ProfileScene(scene_id=escena), ProfileScene(scene_id=otra, position=1)),
    )
    repository.upsert(perfil)

    scenes.delete(escena)

    guardado = repository.get(perfil.id)
    assert guardado is not None
    assert [link.scene_id for link in guardado.scenes] == [otra]


def test_borrar_un_perfil_inexistente_devuelve_false(
    repository: SQLModelProfileRepository,
) -> None:
    assert repository.delete(uuid4()) is False


def test_un_perfil_hacia_una_escena_inexistente_es_una_peticion_invalida(
    repository: SQLModelProfileRepository,
) -> None:
    perfil = Profile(id=uuid4(), name="Roto", scenes=(ProfileScene(scene_id=uuid4()),))

    with pytest.raises(ValueError, match="no existe"):
        repository.upsert(perfil)


def test_el_catalogo_se_lista_ordenado_por_nombre(
    repository: SQLModelProfileRepository,
) -> None:
    repository.upsert(Profile(id=uuid4(), name="Work"))
    repository.upsert(Profile(id=uuid4(), name="Gaming"))

    assert [profile.name for profile in repository.list_all()] == ["Gaming", "Work"]
