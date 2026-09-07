"""Mapper y repositorio de escenas contra SQLite real, en memoria.

Aqui se comprueban las dos cosas que solo la base puede responder: que el viaje
de ida y vuelta conserva la escena entera, y que las reglas de borrado de
`scene_targets` -- CASCADE hacia el dispositivo, RESTRICT hacia el efecto -- son
de verdad y no decoracion del esquema (dependen de `PRAGMA foreign_keys=ON`).
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from backend.app.application.errors import EffectInUseError
from backend.app.domain.effects.models import EffectDefinition, EffectStep, EffectType
from backend.app.domain.lighting import RGBColor
from backend.app.domain.scenes.models import Scene, SceneTarget
from backend.app.infrastructure.persistence.database import (
    IN_MEMORY_URL,
    create_all,
    create_database_engine,
)
from backend.app.infrastructure.persistence.models.device import DeviceRecord
from backend.app.infrastructure.persistence.models.scene import SceneTargetRecord
from backend.app.infrastructure.persistence.repositories import (
    SQLModelEffectRepository,
    SQLModelSceneRepository,
)

MORADO = RGBColor.from_hex("#7B00FF")
AZUL = RGBColor.from_hex("#009DFF")

SALON = UUID("11111111-1111-1111-1111-111111111111")
DORMITORIO = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = create_database_engine(url=IN_MEMORY_URL)
    create_all(eng)
    with Session(eng) as session:
        session.add(DeviceRecord(id=SALON, name="Salon", adapter_type="null"))
        session.add(DeviceRecord(id=DORMITORIO, name="Dormitorio", adapter_type="null"))
        session.commit()
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture
def repository(session: Session) -> SQLModelSceneRepository:
    return SQLModelSceneRepository(session)


@pytest.fixture
def effects(session: Session) -> SQLModelEffectRepository:
    return SQLModelEffectRepository(session)


def _efecto(repository: SQLModelEffectRepository, nombre: str = "Morado fijo") -> UUID:
    definicion = EffectDefinition(
        id=uuid4(),
        name=nombre,
        type=EffectType.STATIC,
        steps=(EffectStep(position=0, color=MORADO),),
    )
    return repository.upsert(definicion).id


def _escena(effect_id: UUID, *, nombre: str = "Noche") -> Scene:
    return Scene(
        id=uuid4(),
        name=nombre,
        description="Para leer",
        icon="moon",
        is_favorite=True,
        targets=(SceneTarget(device_id=SALON, effect_id=effect_id, brightness=10, speed=30),),
    )


def test_una_escena_completa_sobrevive_al_viaje_de_ida_y_vuelta(
    repository: SQLModelSceneRepository, effects: SQLModelEffectRepository
) -> None:
    escena = _escena(_efecto(effects))

    repository.upsert(escena)

    assert repository.get(escena.id) == escena


def test_guardar_dos_veces_reemplaza_los_objetivos_sin_violar_el_unique(
    repository: SQLModelSceneRepository, effects: SQLModelEffectRepository
) -> None:
    """El UNIQUE (scene_id, device_id) exige que los DELETE precedan a los INSERT."""
    efecto = _efecto(effects)
    escena = _escena(efecto)
    repository.upsert(escena)

    reemplazada = escena.model_copy(
        update={
            "targets": (
                SceneTarget(device_id=SALON, effect_id=efecto, brightness=80),
                SceneTarget(device_id=DORMITORIO, effect_id=efecto, enabled=False),
            )
        }
    )
    guardada = repository.upsert(reemplazada)

    assert len(guardada.targets) == 2
    assert {target.device_id for target in guardada.targets} == {SALON, DORMITORIO}


def test_los_objetivos_se_leen_siempre_en_el_mismo_orden(
    repository: SQLModelSceneRepository, effects: SQLModelEffectRepository
) -> None:
    """`scene_targets` no declara `order_by` y su clave primaria es aleatoria."""
    efecto = _efecto(effects)
    escena = Scene(
        id=uuid4(),
        name="Dos tiras",
        targets=(
            SceneTarget(device_id=DORMITORIO, effect_id=efecto),
            SceneTarget(device_id=SALON, effect_id=efecto),
        ),
    )

    guardada = repository.upsert(escena)

    assert [target.device_id for target in guardada.targets] == [SALON, DORMITORIO]


def test_la_activacion_trae_solo_los_objetivos_habilitados_con_su_efecto(
    repository: SQLModelSceneRepository, effects: SQLModelEffectRepository
) -> None:
    efecto = _efecto(effects, nombre="Morado")
    otro = _efecto(effects, nombre="Azul")
    escena = Scene(
        id=uuid4(),
        name="Mixta",
        targets=(
            SceneTarget(device_id=SALON, effect_id=efecto, brightness=25),
            SceneTarget(device_id=DORMITORIO, effect_id=otro, enabled=False),
        ),
    )
    repository.upsert(escena)

    activacion = repository.get_activation(escena.id)

    assert activacion is not None
    assert [item.target.device_id for item in activacion.targets] == [SALON]
    assert activacion.targets[0].effect.id == efecto
    assert activacion.targets[0].effect.steps[0].color == MORADO
    # La escena completa sigue llevando los dos objetivos: uno es lo que se
    # reproduce y otro lo que se edita.
    assert len(activacion.scene.targets) == 2


def test_la_activacion_de_una_escena_inexistente_es_none(
    repository: SQLModelSceneRepository,
) -> None:
    assert repository.get_activation(uuid4()) is None


def test_una_escena_sin_objetivos_habilitados_si_existe(
    repository: SQLModelSceneRepository, effects: SQLModelEffectRepository
) -> None:
    """No es lo mismo "no esta" (404) que "no hay nada que reproducir" (409)."""
    escena = Scene(
        id=uuid4(),
        name="Apagada",
        targets=(SceneTarget(device_id=SALON, effect_id=_efecto(effects), enabled=False),),
    )
    repository.upsert(escena)

    activacion = repository.get_activation(escena.id)

    assert activacion is not None
    assert activacion.targets == ()


def test_borrar_un_efecto_que_usa_una_escena_falla_por_restrict(
    repository: SQLModelSceneRepository,
    effects: SQLModelEffectRepository,
) -> None:
    """RESTRICT: la escena no puede quedarse sin nada que ejecutar.

    Lo que sube NO es el `IntegrityError` crudo: dejarlo pasar lo convertia en un
    `500 internal_error` en la API, y borrar un efecto en uso es un error del
    usuario (409). La traduccion vive en el repositorio porque la capa de
    aplicacion no puede importar SQLAlchemy.
    """
    efecto = _efecto(effects)
    repository.upsert(_escena(efecto))

    with pytest.raises(EffectInUseError, match=str(efecto)):
        effects.delete(efecto)

    # El repositorio ya deshizo la transaccion fallida: la sesion sigue usable
    # sin que el llamante tenga que saber que hubo un `IntegrityError`.
    assert effects.get(efecto) is not None
    assert repository.list_all() != []


def test_borrar_un_dispositivo_se_lleva_los_objetivos_en_cascada(
    session: Session,
    repository: SQLModelSceneRepository,
    effects: SQLModelEffectRepository,
) -> None:
    """La asimetria con el efecto es deliberada (ARCHITECTURE 7.5) y silenciosa.

    Es tambien la razon por la que hoy no existe `DELETE /devices/{id}`.
    """
    escena = _escena(_efecto(effects))
    repository.upsert(escena)

    dispositivo = session.get(DeviceRecord, SALON)
    assert dispositivo is not None
    session.delete(dispositivo)
    session.commit()

    assert session.exec(select(SceneTargetRecord)).all() == []
    assert repository.get(escena.id) is not None


def test_borrar_una_escena_no_borra_los_efectos_que_usaba(
    repository: SQLModelSceneRepository, effects: SQLModelEffectRepository
) -> None:
    efecto = _efecto(effects)
    escena = _escena(efecto)
    repository.upsert(escena)

    assert repository.delete(escena.id) is True
    assert repository.get(escena.id) is None
    assert effects.get(efecto) is not None


def test_borrar_una_escena_inexistente_devuelve_false(
    repository: SQLModelSceneRepository,
) -> None:
    """El 404 lo decide el caso de uso, no el SQL."""
    assert repository.delete(uuid4()) is False


def test_un_objetivo_hacia_un_efecto_inexistente_es_una_peticion_invalida(
    repository: SQLModelSceneRepository,
) -> None:
    """Traducido a `ValueError` (422): un 500 no le diria al cliente que corregir."""
    escena = Scene(
        id=uuid4(),
        name="Rota",
        targets=(SceneTarget(device_id=SALON, effect_id=uuid4()),),
    )

    with pytest.raises(ValueError, match="no existe"):
        repository.upsert(escena)


def test_la_sesion_sigue_siendo_usable_tras_una_clave_foranea_invalida(
    repository: SQLModelSceneRepository, effects: SQLModelEffectRepository
) -> None:
    """Sin el `rollback()`, la siguiente consulta fallaria por una causa distinta."""
    rota = Scene(
        id=uuid4(),
        name="Rota",
        targets=(SceneTarget(device_id=SALON, effect_id=uuid4()),),
    )
    with pytest.raises(ValueError, match="no existe"):
        repository.upsert(rota)

    valida = _escena(_efecto(effects))

    assert repository.upsert(valida).id == valida.id


def test_el_catalogo_se_lista_ordenado_por_nombre(
    repository: SQLModelSceneRepository, effects: SQLModelEffectRepository
) -> None:
    efecto = _efecto(effects)
    repository.upsert(_escena(efecto, nombre="Zen"))
    repository.upsert(_escena(efecto, nombre="Amanecer"))

    assert [scene.name for scene in repository.list_all()] == ["Amanecer", "Zen"]
