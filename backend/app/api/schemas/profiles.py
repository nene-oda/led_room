"""DTOs de perfiles: cuerpos de escritura y lectura del catalogo.

Dos decisiones del contrato:

* **La posicion de una escena es su indice en el array**, y no un campo. Misma
  regla que los pasos de un efecto: asi dos escenas en la misma posicion son
  irrepresentables en vez de ser un 422 que haya que redactar. La posicion si se
  publica al leer, porque el orden es informacion que la UI necesita y no tiene
  por que deducirlo del array.
* **`brightness_limit` del README 14 no existe.** La tabla `profiles` no tiene la
  columna y un tope de brillo solo significa algo si el perfil sigue "puesto" y
  acota tambien los comandos manuales posteriores; hoy activar un perfil es un
  disparo puntual que delega en una escena. Adoptarlo seria una migracion nueva y
  un clamp al construir el `EffectPlan`, nunca dentro del renderer
  (NEXT_STEPS 6.7).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.api.schemas.state import SceneStatusRead
from backend.app.domain.profiles.models import (
    ICON_MAX_LENGTH,
    NAME_MAX_LENGTH,
    Profile,
    ProfileScene,
)
from backend.app.domain.state import SceneStatus


class ProfileSceneWrite(BaseModel):
    """Una escena dentro del perfil. Su posicion es el indice en el array."""

    scene_id: UUID

    #: Marca la escena que activa `POST /profiles/{id}/activate`. Si hay varias
    #: marcadas -- o ninguna -- el servidor resuelve de forma determinista: gana
    #: la de menor posicion y, en empate, el `scene_id` menor.
    is_default: bool = False

    def to_domain(self, position: int) -> ProfileScene:
        return ProfileScene(
            scene_id=self.scene_id,
            position=position,
            is_default=self.is_default,
        )


class ProfileWrite(BaseModel):
    """Cuerpo de `POST /profiles` y de `PUT /profiles/{id}`."""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=ICON_MAX_LENGTH, examples=["gamepad"])

    scenes: list[ProfileSceneWrite] = Field(default_factory=list)

    def to_domain(self, profile_id: UUID) -> Profile:
        return Profile(
            id=profile_id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            scenes=tuple(scene.to_domain(position) for position, scene in enumerate(self.scenes)),
        )


class ProfileSceneRead(BaseModel):
    scene_id: str
    position: int = Field(ge=0)
    is_default: bool

    @classmethod
    def from_domain(cls, link: ProfileScene) -> ProfileSceneRead:
        return cls(
            scene_id=str(link.scene_id),
            position=link.position,
            is_default=link.is_default,
        )


class ProfileRead(BaseModel):
    """Un perfil tal y como se publica."""

    id: str
    name: str
    description: str | None = None
    icon: str | None = None
    is_builtin: bool
    scenes: list[ProfileSceneRead]

    #: Que escena activaria el perfil ahora mismo. Se publica resuelta para que
    #: la UI no tenga que reimplementar el desempate (y no pueda equivocarse).
    default_scene_id: str | None = None

    @classmethod
    def from_domain(cls, profile: Profile) -> ProfileRead:
        default = profile.default_scene_id()
        return cls(
            id=str(profile.id),
            name=profile.name,
            description=profile.description,
            icon=profile.icon,
            is_builtin=profile.is_builtin,
            scenes=[ProfileSceneRead.from_domain(link) for link in profile.scenes],
            default_scene_id=None if default is None else str(default),
        )


class ProfileActivationRead(BaseModel):
    """Resultado de activar un perfil: que escena quedo puesta.

    Se devuelve la escena y no solo un 204 porque el perfil resuelve **cual** de
    sus escenas se activa, y el cliente que pulso el boton no tiene por que
    repetir esa resolucion para saber que resaltar.
    """

    profile_id: str
    scene: SceneStatusRead

    @classmethod
    def from_domain(cls, profile_id: UUID, scene: SceneStatus) -> ProfileActivationRead:
        return cls(profile_id=str(profile_id), scene=SceneStatusRead.from_domain(scene))
