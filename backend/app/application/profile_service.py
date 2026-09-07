"""Casos de uso de perfiles: catalogo y activacion (NEXT_STEPS 6.7).

Un perfil se activa **delegando** en el caso de uso de escenas, exactamente
igual que una escena se reproduce delegando en el reproductor de efectos:

```text
ProfileService -> SceneService -> EffectPlayer -> EffectRunner -> LightDevicePort
```

Aqui no hay ni una linea de activacion propia. Reimplementarla seria la tercera
copia de la misma secuencia, y la primera que se olvidara de validar antes de
tocar el hardware dejaria la habitacion a medias.

Lo unico que este modulo decide es **cual** de las escenas del perfil se activa,
y ni siquiera eso es suyo: la regla vive en `Profile.default_scene_id`, que es
una funcion pura y esta en el dominio.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol
from uuid import UUID, uuid4

from backend.app.application.errors import NothingToActivateError, ProfileNotFoundError
from backend.app.domain.profiles.models import Profile
from backend.app.domain.profiles.repositories import ProfileRepository
from backend.app.domain.state import SceneStatus


class SceneActivator(Protocol):
    """Lo unico que este caso de uso necesita de las escenas: activar una.

    Protocolo estrecho y declarado por el consumidor (segregacion de
    interfaces): tipar contra `SceneService` entero ataria los perfiles al CRUD
    de escenas y obligaria a construir un servicio completo para probar la
    delegacion.
    """

    async def activate(self, scene_id: UUID) -> SceneStatus: ...


class ProfileService:
    """Catalogo de perfiles y activacion del perfil.

    De **vida corta**, uno por peticion, como el resto de servicios que usan un
    repositorio.
    """

    def __init__(
        self,
        *,
        repository: ProfileRepository,
        scenes: SceneActivator,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository = repository
        self._scenes = scenes
        self._new_id = new_id

    def list_profiles(self) -> Sequence[Profile]:
        """Metodo sincrono: solo lee el repositorio."""
        return self._repository.list_all()

    def get_profile(self, profile_id: UUID) -> Profile:
        profile = self._repository.get(profile_id)
        if profile is None:
            raise ProfileNotFoundError(f"No hay ningun perfil guardado con id {profile_id}.")
        return profile

    def save(self, profile: Profile) -> Profile:
        return self._repository.upsert(profile)

    def delete(self, profile_id: UUID) -> None:
        if not self._repository.delete(profile_id):
            raise ProfileNotFoundError(f"No hay ningun perfil guardado con id {profile_id}.")

    async def activate(self, profile_id: UUID) -> SceneStatus:
        """Resuelve la escena predeterminada del perfil y la activa.

        Todo lo que puede salir mal en la activacion (escena inexistente,
        dispositivo desconectado, capacidad ausente) lo decide y lo señala el
        servicio de escenas: aqui solo se añade el 409 de un perfil sin ninguna
        escena, que es lo unico que este caso de uso puede saber.

        La lectura del repositorio corre en el bucle de eventos, igual que la de
        `SceneService.activate` y por el mismo motivo: sacarla exigiria que esta
        capa importara Starlette. Se acepta porque es una lectura por clave
        primaria y no un `commit()`.
        """
        profile = self.get_profile(profile_id)

        scene_id = profile.default_scene_id()
        if scene_id is None:
            raise NothingToActivateError(
                f"El perfil {profile.name!r} no tiene ninguna escena asociada: "
                "añade al menos una antes de activarlo."
            )

        return await self._scenes.activate(scene_id)
