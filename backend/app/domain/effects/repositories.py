"""Puerto de persistencia de efectos.

Mismas dos reglas que `devices/repositories.py`, por los mismos motivos:

* las firmas hablan **tipos de dominio** (`EffectDefinition`, `UUID`), nunca
  `EffectRecord`: un servicio tipado contra SQLModel no se puede probar sin base
  de datos ni migrar a otro almacenamiento;
* los metodos son **sincronos**, porque la implementacion usa la `Session`
  sincrona de SQLModel; los que hacen `commit()` se llaman desde el threadpool.

Protocolo estrecho: exactamente el CRUD que la Fase 5 necesita. **Ningun
`LightFrame` se persiste jamas**, asi que aqui no hay nada que los mencione.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from backend.app.domain.effects.models import EffectDefinition


@runtime_checkable
class EffectRepository(Protocol):
    """Lectura y escritura del catalogo de efectos."""

    def get(self, effect_id: UUID) -> EffectDefinition | None: ...

    def list_all(self) -> Sequence[EffectDefinition]:
        """Catalogo completo, en orden estable por nombre."""
        ...

    def upsert(self, effect: EffectDefinition) -> EffectDefinition:
        """Crea o reemplaza por `id`, pasos incluidos. Devuelve lo persistido."""
        ...

    def delete(self, effect_id: UUID) -> bool:
        """Borra. `False` si no existia, para que el llamante decida el 404.

        Un efecto al que apunte alguna escena **no se puede borrar**: la
        implementacion señala ese caso con una excepcion (409), en vez de
        devolver `False`, porque "no existe" y "existe pero esta en uso" llevan a
        la UI a dos sitios distintos. El tipo concreto lo fija la capa de
        aplicacion; nombrarlo aqui invertiria la direccion de las dependencias.
        """
        ...
