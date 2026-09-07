"""DTOs de escenas: cuerpos de escritura y lectura del catalogo.

Tres decisiones del contrato que no son evidentes:

* **Una escena referencia efectos; no los lleva dentro.** El README 13 dibuja la
  escena con el efecto incrustado (`{"effect": {"type": "static", "colors":
  [...]}}`), pero el esquema congelado dice otra cosa: `scene_targets` exige
  `device_id` y `effect_id`, y ninguno de los dos aparece en aquel dibujo.
  Aceptar el efecto incrustado significaria crear filas de `effects` sin dueño
  desde el endpoint de escenas: no saldrian en el catalogo por voluntad de
  nadie, nadie sabria cuando borrarlas y habria dos caminos para crear un
  efecto. Para una escena de color fijo, el camino es `POST /effects` con
  `type: STATIC` y un paso, y luego referenciar ese `effect_id`.
* **El brillo y la velocidad de la escena son anulaciones POR OBJETIVO**, no
  campos de la escena: son exactamente los dos parametros que acepta el motor al
  construir el plan, y ponerlos en la escena obligaria a repartirlos a mano
  entre los objetivos.
* **Los identificadores se leen como cadena y se escriben como `UUID`**: al
  escribir, el tipo valida el formato y devuelve un 422 legible; al leer, el
  JSON no tiene tipo UUID y el frontend no debe inventarse la conversion. Es la
  misma regla que ya siguen dispositivos y efectos.

`is_builtin` no se acepta al escribir: lo decide el servidor, y aceptarlo
dejaria que un cliente marcara como "de fabrica" una escena que creo el.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.domain.effects.models import SPEED_MAX, SPEED_MIN
from backend.app.domain.lighting import Percent
from backend.app.domain.scenes.models import (
    ICON_MAX_LENGTH,
    NAME_MAX_LENGTH,
    Scene,
    SceneTarget,
)


class SceneTargetWrite(BaseModel):
    """Que efecto aplica la escena sobre un dispositivo."""

    device_id: UUID
    effect_id: UUID

    #: `None` = usa el brillo del efecto. No es lo mismo que 0.
    brightness: Percent | None = None

    #: `None` = usa la velocidad del efecto. Multiplicador, no una duracion.
    speed: int | None = Field(default=None, ge=SPEED_MIN, le=SPEED_MAX)

    #: Un objetivo deshabilitado se guarda pero no se reproduce.
    enabled: bool = True

    def to_domain(self) -> SceneTarget:
        return SceneTarget(
            device_id=self.device_id,
            effect_id=self.effect_id,
            brightness=self.brightness,
            speed=self.speed,
            enabled=self.enabled,
        )


class SceneWrite(BaseModel):
    """Cuerpo de `POST /scenes` y de `PUT /scenes/{id}`.

    Los rangos se repiten aunque `Scene` ya los valide, por el mismo motivo que
    en `EffectWrite`: este modelo protege el contrato **publicado** y lo
    documenta en el OpenAPI; el de dominio protege la invariante del modelo.
    """

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = None

    #: Nombre de icono para la UI. El backend no lo interpreta.
    icon: str | None = Field(default=None, max_length=ICON_MAX_LENGTH, examples=["moon"])

    is_favorite: bool = False

    targets: list[SceneTargetWrite] = Field(default_factory=list)

    def to_domain(self, scene_id: UUID) -> Scene:
        """Construye la escena de dominio, que es quien valida de verdad.

        Que no haya dos objetivos para el mismo dispositivo NO se comprueba
        aqui: es una invariante del modelo y repetirla en el DTO seria una
        segunda copia de la regla.
        """
        return Scene(
            id=scene_id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            is_favorite=self.is_favorite,
            targets=tuple(target.to_domain() for target in self.targets),
        )


class SceneDuplicateRequest(BaseModel):
    """Cuerpo opcional de `POST /scenes/{id}/duplicate`.

    Sin `name`, el servidor añade el sufijo de copia. Poder darlo evita el
    duplicar-y-renombrar en dos peticiones desde la UI.
    """

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)


class SceneTargetRead(BaseModel):
    device_id: str
    effect_id: str
    brightness: Percent | None = None
    speed: int | None = None
    enabled: bool

    @classmethod
    def from_domain(cls, target: SceneTarget) -> SceneTargetRead:
        return cls(
            device_id=str(target.device_id),
            effect_id=str(target.effect_id),
            brightness=target.brightness,
            speed=target.speed,
            enabled=target.enabled,
        )


class SceneRead(BaseModel):
    """Una escena tal y como se publica."""

    id: str
    name: str
    description: str | None = None
    icon: str | None = None
    is_builtin: bool
    is_favorite: bool
    targets: list[SceneTargetRead]

    @classmethod
    def from_domain(cls, scene: Scene) -> SceneRead:
        return cls(
            id=str(scene.id),
            name=scene.name,
            description=scene.description,
            icon=scene.icon,
            is_builtin=scene.is_builtin,
            is_favorite=scene.is_favorite,
            targets=[SceneTargetRead.from_domain(target) for target in scene.targets],
        )
