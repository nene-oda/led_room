"""Tabla `schedules` (LED_ROOM_DATABASE_MODEL 16 y 46).

La tabla existe, pero todavia no hay planificador que la lea.
Sin `from __future__ import annotations`: ver la nota de `device.py`.
"""

import datetime as dt
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint
from sqlmodel import Field, Relationship, SQLModel

from backend.app.infrastructure.persistence.models.base import UtcDateTime, utc_now

if TYPE_CHECKING:  # pragma: no cover
    from backend.app.infrastructure.persistence.models.profile import ProfileRecord
    from backend.app.infrastructure.persistence.models.scene import SceneRecord


class ScheduleRecord(SQLModel, table=True):
    """Activa una escena O un perfil a una hora dada. Nunca las dos cosas."""

    __tablename__ = "schedules"

    __table_args__ = (
        CheckConstraint(
            "(scene_id IS NOT NULL AND profile_id IS NULL) "
            "OR (scene_id IS NULL AND profile_id IS NOT NULL)",
            name="ck_schedules_single_target",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    name: str = Field(max_length=120)
    enabled: bool = Field(default=True, index=True)

    #: El atributo NO se llama `time`, como propone el documento 46: el nombre
    #: del campo entra en el espacio de nombres de la clase y ensombreceria al
    #: tipo `datetime.time` al resolver la anotacion. `at_time` lo evita.
    at_time: dt.time = Field(index=True)

    #: Sin planificador todavia, el formato lo fijara el dominio cuando exista
    #: (por ejemplo "MO,TU,WE"). Hoy es texto libre a proposito.
    days_of_week: Optional[str] = Field(default=None, max_length=50)  # noqa: UP045

    scene_id: Optional[UUID] = Field(  # noqa: UP045
        default=None, foreign_key="scenes.id", ondelete="CASCADE"
    )
    profile_id: Optional[UUID] = Field(  # noqa: UP045
        default=None, foreign_key="profiles.id", ondelete="CASCADE"
    )

    created_at: dt.datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)
    updated_at: dt.datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)

    scene: Optional["SceneRecord"] = Relationship()
    profile: Optional["ProfileRecord"] = Relationship()
