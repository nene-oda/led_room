"""Modelo de dominio de un perfil (README 14, NEXT_STEPS 6.7).

```text
Profile ──* ProfileScene ──> (scene_id, position, is_default)
```

**La unica regla de negocio del perfil es cual es su escena predeterminada**, y
vive aqui, en el dominio, no en el servicio: es una funcion pura de sus datos y
tiene que dar siempre el mismo resultado, tambien cuando los datos son
contradictorios (dos escenas marcadas, o ninguna).

`brightness_limit` del README 14 **no** esta modelado. La discrepancia se
resuelve a favor del esquema y se documenta en el informe de la Fase 7: la tabla
`profiles` no tiene la columna, ningun consumidor lo lee y, sobre todo, un tope
de brillo solo significa algo si el perfil sigue "puesto" y acota tambien los
comandos manuales posteriores -- y un perfil hoy es una activacion puntual, no un
modo persistente. Adoptarlo seria una migracion nueva y un clamp al construir el
`EffectPlan`, nunca dentro del renderer.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Cotas de las columnas de texto de `profiles`, iguales a las de `scenes`.
NAME_MAX_LENGTH = 120
ICON_MAX_LENGTH = 80


class ProfileScene(BaseModel):
    """Una escena dentro de un perfil, con su orden y su marca de predeterminada."""

    model_config = ConfigDict(frozen=True)

    scene_id: UUID

    #: Orden de presentacion. Es tambien el primer criterio de desempate al
    #: resolver la escena predeterminada.
    position: int = Field(default=0, ge=0)

    is_default: bool = False


class Profile(BaseModel):
    """Un contexto de uso que agrupa escenas relacionadas."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=ICON_MAX_LENGTH)

    is_builtin: bool = False

    #: Tupla y no lista: el perfil es inmutable de arriba a abajo.
    scenes: tuple[ProfileScene, ...] = ()

    @model_validator(mode="after")
    def _check_invariants(self) -> Profile:
        identifiers = [link.scene_id for link in self.scenes]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(
                "Un perfil no puede contener dos veces la misma escena: "
                "la clave primaria de `profile_scenes` es (profile_id, scene_id)."
            )
        return self

    def default_scene_id(self) -> UUID | None:
        """Que escena activa el perfil. `None` si no tiene ninguna.

        **Determinista incluso con datos contradictorios**, que es justo lo que
        hace que esta regla merezca vivir en el dominio:

        1. mandan las marcadas `is_default`; si no hay ninguna, valen todas;
        2. entre ellas gana la de menor `position`;
        3. y si dos empatan, gana el `scene_id` menor.

        El tercer criterio no es decorativo: sin el, un perfil con dos escenas en
        la misma posicion activaria una u otra segun el orden en que la base
        devolviera las filas, y el mismo boton haria dos cosas distintas.
        """
        marked = tuple(link for link in self.scenes if link.is_default)
        candidates = marked or self.scenes
        if not candidates:
            return None

        return min(candidates, key=lambda link: (link.position, link.scene_id)).scene_id
