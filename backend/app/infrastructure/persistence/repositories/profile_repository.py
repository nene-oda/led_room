"""`ProfileRepository` sobre la `Session` sincrona de SQLModel.

Calcado del repositorio de escenas, y deliberadamente **no** extraido a una base
comun: lo unico que comparten es la forma del CRUD, mientras que lo que decide
cada metodo (que relacion hija se reemplaza, que UNIQUE hay que respetar, que
mensaje se le da al cliente) es distinto en cada tabla. Una clase base generica
obligaria a parametrizar mapper, modelo, relacion y clave, y seria mas dificil de
leer que las dos versiones explicitas.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from backend.app.domain.profiles.models import Profile
from backend.app.infrastructure.persistence.mappers.profile import (
    apply_profile_to_record,
    profile_to_domain,
    scene_link_records,
)
from backend.app.infrastructure.persistence.models.profile import ProfileRecord


class SQLModelProfileRepository:
    """Cumple el Protocol `backend.app.domain.profiles.repositories.ProfileRepository`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, profile_id: UUID) -> Profile | None:
        record = self._session.get(ProfileRecord, profile_id)
        return None if record is None else profile_to_domain(record)

    def list_all(self) -> Sequence[Profile]:
        """Catalogo completo, en orden estable por nombre."""
        statement = select(ProfileRecord).order_by(col(ProfileRecord.name))
        return [profile_to_domain(record) for record in self._session.exec(statement).all()]

    def upsert(self, profile: Profile) -> Profile:
        """Crea o reemplaza por `id`, escenas incluidas."""
        record = self._session.get(ProfileRecord, profile.id)
        if record is None:
            record = ProfileRecord(id=profile.id)
            self._session.add(record)

        apply_profile_to_record(record, profile)

        # Mismo motivo que en escenas y efectos: la clave primaria de
        # `profile_scenes` es (profile_id, scene_id), asi que los DELETE tienen
        # que llegar a la base antes que los INSERT de la nueva lista.
        record.scene_links.clear()
        self._session.flush()
        record.scene_links.extend(scene_link_records(record, profile))

        self._commit()
        self._session.refresh(record)
        return profile_to_domain(record)

    def delete(self, profile_id: UUID) -> bool:
        """`False` si no existia. Borrar un perfil no borra sus escenas.

        Solo se van los enlaces, por el `ON DELETE CASCADE` de `profile_scenes`:
        una escena es catalogo compartido y puede estar en otros perfiles.
        """
        record = self._session.get(ProfileRecord, profile_id)
        if record is None:
            return False

        self._session.delete(record)
        self._session.commit()
        return True

    def _commit(self) -> None:
        """Confirma traduciendo la violacion de clave foranea a `ValueError` (422)."""
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ValueError(
                "El perfil referencia alguna escena que no existe: crea la escena "
                "antes de añadirla al perfil."
            ) from error
