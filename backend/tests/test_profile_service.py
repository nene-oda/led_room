"""Casos de uso de perfiles: resolver la escena y **delegar**.

Se prueba con un doble de `SceneActivator` a proposito: lo que hay que demostrar
es que este servicio no construye planes ni toca el reproductor, sino que le pasa
la pelota al caso de uso de escenas. Con un `SceneService` real, un servicio que
reimplementara la activacion pasaria estos tests igual.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.app.application.errors import NothingToActivateError, ProfileNotFoundError
from backend.app.application.profile_service import ProfileService
from backend.app.domain.profiles.models import Profile, ProfileScene
from backend.tests.doubles import InMemoryProfileRepository, RecordingSceneActivator

ESCENA_A = UUID("aaaaaaaa-0000-0000-0000-000000000000")
ESCENA_B = UUID("bbbbbbbb-0000-0000-0000-000000000000")
COPIA = UUID("99999999-9999-9999-9999-999999999999")


def _servicio(
    *profiles: Profile,
) -> tuple[ProfileService, RecordingSceneActivator, InMemoryProfileRepository]:
    repository = InMemoryProfileRepository(profiles)
    scenes = RecordingSceneActivator()
    service = ProfileService(repository=repository, scenes=scenes, new_id=lambda: COPIA)
    return service, scenes, repository


@pytest.mark.asyncio
async def test_activar_un_perfil_delega_en_el_caso_de_uso_de_escenas() -> None:
    perfil = Profile(
        id=uuid4(),
        name="Gaming",
        scenes=(
            ProfileScene(scene_id=ESCENA_A, position=0),
            ProfileScene(scene_id=ESCENA_B, position=1, is_default=True),
        ),
    )
    service, scenes, _ = _servicio(perfil)

    estado = await service.activate(perfil.id)

    assert scenes.activated == [ESCENA_B]
    assert estado.id == ESCENA_B


@pytest.mark.asyncio
async def test_activar_un_perfil_sin_escenas_es_un_409() -> None:
    perfil = Profile(id=uuid4(), name="Vacio")
    service, scenes, _ = _servicio(perfil)

    with pytest.raises(NothingToActivateError, match="Vacio"):
        await service.activate(perfil.id)

    assert scenes.activated == []


@pytest.mark.asyncio
async def test_activar_un_perfil_inexistente_es_un_404() -> None:
    service, scenes, _ = _servicio()

    with pytest.raises(ProfileNotFoundError):
        await service.activate(uuid4())

    assert scenes.activated == []


@pytest.mark.asyncio
async def test_el_perfil_no_decide_por_su_cuenta_cual_es_la_escena() -> None:
    """La regla vive en el dominio: aqui solo se comprueba que se usa esa y no otra."""
    perfil = Profile(
        id=uuid4(),
        name="Relax",
        scenes=(
            ProfileScene(scene_id=ESCENA_B, position=1),
            ProfileScene(scene_id=ESCENA_A, position=0),
        ),
    )
    service, scenes, _ = _servicio(perfil)

    await service.activate(perfil.id)

    assert scenes.activated == [perfil.default_scene_id()]


def test_borrar_un_perfil_inexistente_es_un_404() -> None:
    service, _, _ = _servicio()

    with pytest.raises(ProfileNotFoundError):
        service.delete(uuid4())


def test_guardar_un_perfil_lo_devuelve_persistido() -> None:
    service, _, repository = _servicio()
    perfil = Profile(id=uuid4(), name="Work")

    assert service.save(perfil) == perfil
    assert repository.get(perfil.id) == perfil
