"""Puerto de persistencia de escenas.

Mismas dos reglas que `devices/repositories.py` y `effects/repositories.py`:
las firmas hablan **tipos de dominio** (`Scene`, `SceneActivation`, `UUID`) y los
metodos son **sincronos**, porque la implementacion usa la `Session` sincrona de
SQLModel. Los que hacen `commit()` se llaman desde el threadpool.

`get_activation` no es un `get` con azucar: resuelve objetivos y efectos **en
una sola consulta** porque activar una escena no puede costar una consulta por
objetivo (NEXT_STEPS 6.7, paso 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from backend.app.domain.scenes.models import Scene, SceneActivation


@runtime_checkable
class SceneRepository(Protocol):
    """Lectura y escritura del catalogo de escenas."""

    def get(self, scene_id: UUID) -> Scene | None: ...

    def list_all(self) -> Sequence[Scene]:
        """Catalogo completo, en orden estable por nombre."""
        ...

    def get_activation(self, scene_id: UUID) -> SceneActivation | None:
        """La escena con sus objetivos habilitados y los efectos ya resueltos.

        `None` si la escena no existe. Una escena existente **sin** objetivos
        habilitados devuelve una activacion con `targets` vacio: no es lo mismo
        "no esta" (404) que "no hay nada que reproducir" (409).
        """
        ...

    def upsert(self, scene: Scene) -> Scene:
        """Crea o reemplaza por `id`, objetivos incluidos. Devuelve lo persistido."""
        ...

    def delete(self, scene_id: UUID) -> bool:
        """Borra. `False` si no existia, para que el llamante decida el 404."""
        ...
