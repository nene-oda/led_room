"""Tablas `scenes` y `scene_targets` (LED_ROOM_DATABASE_MODEL 11-13 y 44).

Sin `from __future__ import annotations`: ver la nota de `device.py`.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from backend.app.infrastructure.persistence.models.base import UtcDateTime, utc_now

if TYPE_CHECKING:  # pragma: no cover
    from backend.app.infrastructure.persistence.models.device import DeviceRecord
    from backend.app.infrastructure.persistence.models.effect import EffectRecord
    from backend.app.infrastructure.persistence.models.profile import ProfileSceneRecord


class SceneRecord(SQLModel, table=True):
    """Una configuracion que el usuario puede activar."""

    __tablename__ = "scenes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    name: str = Field(max_length=120, index=True)
    description: Optional[str] = Field(default=None)  # noqa: UP045
    icon: Optional[str] = Field(default=None, max_length=80)  # noqa: UP045

    is_builtin: bool = Field(default=False)
    is_favorite: bool = Field(default=False)

    created_at: datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)
    updated_at: datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)

    targets: list["SceneTargetRecord"] = Relationship(
        back_populates="scene",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    profile_links: list["ProfileSceneRecord"] = Relationship(
        back_populates="scene",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SceneTargetRecord(SQLModel, table=True):
    """Que efecto aplica una escena sobre que dispositivo.

    La escena no apunta a un efecto directamente para que manana pueda dar un
    efecto distinto a cada tira (LED_ROOM_DATABASE_MODEL 13).
    """

    __tablename__ = "scene_targets"

    __table_args__ = (
        UniqueConstraint("scene_id", "device_id", name="uq_scene_targets_scene_device"),
        CheckConstraint(
            "brightness IS NULL OR (brightness >= 0 AND brightness <= 100)",
            name="ck_scene_targets_brightness",
        ),
        CheckConstraint(
            "speed IS NULL OR (speed >= 0 AND speed <= 100)",
            name="ck_scene_targets_speed",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    scene_id: UUID = Field(foreign_key="scenes.id", ondelete="CASCADE", index=True)
    device_id: UUID = Field(foreign_key="devices.id", ondelete="CASCADE", index=True)

    #: RESTRICT: borrar un efecto que una escena usa debe fallar, no dejar la
    #: escena sin nada que ejecutar.
    effect_id: UUID = Field(foreign_key="effects.id", ondelete="RESTRICT", index=True)

    brightness: Optional[int] = Field(default=None, ge=0, le=100)  # noqa: UP045
    speed: Optional[int] = Field(default=None, ge=0, le=100)  # noqa: UP045

    enabled: bool = Field(default=True)

    scene: "SceneRecord" = Relationship(back_populates="targets")
    device: "DeviceRecord" = Relationship(back_populates="scene_targets")
    effect: "EffectRecord" = Relationship()
