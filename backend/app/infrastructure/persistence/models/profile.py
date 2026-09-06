"""Tablas `profiles` y `profile_scenes` (LED_ROOM_DATABASE_MODEL 14-15 y 45).

Sin `from __future__ import annotations`: ver la nota de `device.py`.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint
from sqlmodel import Field, Relationship, SQLModel

from backend.app.infrastructure.persistence.models.base import UtcDateTime, utc_now

if TYPE_CHECKING:  # pragma: no cover
    from backend.app.infrastructure.persistence.models.scene import SceneRecord


class ProfileRecord(SQLModel, table=True):
    """Agrupa escenas relacionadas con un contexto."""

    __tablename__ = "profiles"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    name: str = Field(max_length=120, index=True)
    description: Optional[str] = Field(default=None)  # noqa: UP045
    icon: Optional[str] = Field(default=None, max_length=80)  # noqa: UP045

    is_builtin: bool = Field(default=False)
    is_default: bool = Field(default=False)

    created_at: datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)
    updated_at: datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)

    scene_links: list["ProfileSceneRecord"] = Relationship(
        back_populates="profile",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "ProfileSceneRecord.position",
        },
    )


class ProfileSceneRecord(SQLModel, table=True):
    """Enlace N:M con atributos propios (position, is_default)."""

    __tablename__ = "profile_scenes"

    __table_args__ = (CheckConstraint("position >= 0", name="ck_profile_scenes_position"),)

    profile_id: UUID = Field(foreign_key="profiles.id", ondelete="CASCADE", primary_key=True)

    scene_id: UUID = Field(
        foreign_key="scenes.id",
        ondelete="CASCADE",
        primary_key=True,
        index=True,
    )

    position: int = Field(default=0, ge=0)
    is_default: bool = Field(default=False)

    profile: "ProfileRecord" = Relationship(back_populates="scene_links")
    scene: "SceneRecord" = Relationship(back_populates="profile_links")
