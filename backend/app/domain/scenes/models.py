"""Modelo de dominio de una escena (README 13, NEXT_STEPS 6.7).

```text
Scene ──* SceneTarget ──> (device_id, effect_id, brightness?, speed?)
```

Tres decisiones que sostienen el diseño:

* **Una escena no contiene un efecto: lo referencia.** Asi la misma paleta se
  reutiliza en varias escenas y editarla en un sitio las cambia todas. Es
  tambien lo que exige `scene_targets.effect_id NOT NULL`: una escena de color
  fijo es un efecto `STATIC` de un paso, no un caso especial del modelo
  (ARCHITECTURE 7.5).
* **Un objetivo solo puede anular dos cosas**: `brightness` y `speed`. No son
  campos elegidos por comodidad: son exactamente los dos parametros que
  `engine.build_plan` acepta, y su precedencia ya esta congelada alli. Añadir
  aqui un tercer ajuste obligaria a reimplementar la resolucion del plan.
* **El objetivo no tiene identidad propia.** La clave real es
  `(scene, device)` -- la misma UNIQUE que declara la tabla -- y nadie
  referencia "el objetivo 2 de la escena Noche" desde ningun sitio. Por eso el
  `id` de la fila no sube al dominio: lo genera el repositorio al escribir,
  igual que hace con los pasos de un efecto.

Ningun fotograma aparece por aqui: los `LightFrame` se generan en memoria
durante la reproduccion y no se persisten jamas (NEXT_STEPS 6.10).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.effects.models import EffectDefinition, Speed
from backend.app.domain.lighting import Percent

#: Cotas de las columnas de texto de `scenes`. Se declaran aqui porque el
#: modelo de dominio es quien tiene que hacer irrepresentable un nombre vacio;
#: la base solo lo trunca.
NAME_MAX_LENGTH = 120
ICON_MAX_LENGTH = 80

#: Sufijo de una copia. En el dominio y no en el router: duplicar es una regla
#: del modelo ("una copia no es de fabrica y no comparte identidad"), no una
#: decision del transporte.
COPY_SUFFIX = " (copia)"


class SceneTarget(BaseModel):
    """Que efecto aplica una escena sobre un dispositivo.

    `brightness` y `speed` son **anulaciones**: `None` significa "usa lo del
    efecto", nunca "usa cero" (la misma distincion que en `EffectStep`).
    """

    model_config = ConfigDict(frozen=True)

    device_id: UUID
    effect_id: UUID

    brightness: Percent | None = None
    speed: Speed | None = None

    #: Un objetivo deshabilitado se conserva pero no se activa. Es lo que
    #: permite silenciar una tira sin perder su configuracion en la escena.
    enabled: bool = True


class Scene(BaseModel):
    """Una configuracion completa que el usuario puede activar de un toque."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=ICON_MAX_LENGTH)

    is_builtin: bool = False
    is_favorite: bool = False

    #: Tupla y no lista: la escena es inmutable de arriba a abajo.
    targets: tuple[SceneTarget, ...] = ()

    @model_validator(mode="after")
    def _check_invariants(self) -> Scene:
        devices = [target.device_id for target in self.targets]
        if len(set(devices)) != len(devices):
            raise ValueError(
                "Una escena no puede tener dos objetivos para el mismo dispositivo: "
                "el segundo pisaria al primero sobre la misma tira."
            )
        return self

    @property
    def enabled_targets(self) -> tuple[SceneTarget, ...]:
        """Los objetivos que se reproducen al activar la escena."""
        return tuple(target for target in self.targets if target.enabled)

    def duplicated(self, new_id: UUID, *, name: str | None = None) -> Scene:
        """Una copia con identidad nueva.

        `is_builtin` se apaga siempre: la copia de una escena de fabrica la ha
        creado el usuario y debe poder borrarla. El nombre se recorta a la
        longitud maxima porque duplicar una escena ya larga no puede fallar con
        un 422 por dos palabras que añade el servidor.
        """
        proposed = name if name else f"{self.name}{COPY_SUFFIX}"
        return self.model_copy(
            update={
                "id": new_id,
                "name": proposed[:NAME_MAX_LENGTH],
                "is_builtin": False,
            }
        )


class SceneTargetEffect(BaseModel):
    """Un objetivo habilitado con su efecto **ya cargado**.

    Existe para que activar una escena no dispare una consulta por objetivo: el
    repositorio resuelve objetivos y efectos de una vez y el caso de uso recibe
    todo lo que necesita para construir los planes sin volver a la base.
    """

    model_config = ConfigDict(frozen=True)

    target: SceneTarget
    effect: EffectDefinition


class SceneActivation(BaseModel):
    """Todo lo que hace falta para activar una escena, sin nada mas que leer.

    `targets` contiene **solo los habilitados**, mientras que `scene.targets` los
    lleva todos: la escena es lo que se muestra y se edita, la activacion es lo
    que se reproduce.
    """

    model_config = ConfigDict(frozen=True)

    scene: Scene
    targets: tuple[SceneTargetEffect, ...] = ()
