"""Puerto de persistencia de perfiles.

Mismas reglas que el resto de puertos de repositorio: tipos de dominio en las
firmas, metodos **sincronos** y protocolo estrecho -- exactamente el CRUD que la
Fase 7 necesita, sin un `CrudRepository[T]` generico.

No hay `get_activation` como en las escenas: activar un perfil no reproduce
nada, resuelve una escena y **delega** en el caso de uso de escenas
(NEXT_STEPS 6.7). Un metodo de activacion aqui seria la puerta de entrada a
reimplementar esa activacion.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from backend.app.domain.profiles.models import Profile


@runtime_checkable
class ProfileRepository(Protocol):
    """Lectura y escritura del catalogo de perfiles."""

    def get(self, profile_id: UUID) -> Profile | None: ...

    def list_all(self) -> Sequence[Profile]:
        """Catalogo completo, en orden estable por nombre."""
        ...

    def upsert(self, profile: Profile) -> Profile:
        """Crea o reemplaza por `id`, escenas incluidas. Devuelve lo persistido."""
        ...

    def delete(self, profile_id: UUID) -> bool:
        """Borra. `False` si no existia, para que el llamante decida el 404."""
        ...
