"""Tablas `effects` y `effect_steps` (LED_ROOM_DATABASE_MODEL 8-9 y 42-43).

Sin `from __future__ import annotations`: ver la nota de `device.py`.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from backend.app.infrastructure.persistence.models.base import UtcDateTime, utc_now


class EffectRecord(SQLModel, table=True):
    """Un comportamiento de luz, independiente del hardware.

    El motor decide si se traduce en una transicion temporal (tira analogica de
    hoy) o espacial (tira direccionable futura). La tabla no lo prejuzga
    (LED_ROOM_DATABASE_MODEL 33).
    """

    __tablename__ = "effects"

    __table_args__ = (
        CheckConstraint("speed >= 0 AND speed <= 100", name="ck_effects_speed"),
        CheckConstraint("fps >= 1 AND fps <= 60", name="ck_effects_fps"),
        CheckConstraint("transition_ms >= 0", name="ck_effects_transition_ms"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    name: str = Field(max_length=120, index=True)
    type: str = Field(max_length=40, index=True)
    description: Optional[str] = Field(default=None)  # noqa: UP045

    loop: bool = Field(default=False)
    speed: int = Field(default=50, ge=0, le=100)

    #: La cota 1-60 es la misma que la de Settings.effect_fps; sobre BLE lo
    #: sensato son 10-20 fps.
    fps: int = Field(default=20, ge=1, le=60)
    transition_ms: int = Field(default=1000, ge=0)

    is_builtin: bool = Field(default=False)

    created_at: datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)
    updated_at: datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)

    steps: list["EffectStepRecord"] = Relationship(
        back_populates="effect",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "EffectStepRecord.position",
        },
    )


class EffectStepRecord(SQLModel, table=True):
    """Cada paso o color dentro de un efecto."""

    __tablename__ = "effect_steps"

    __table_args__ = (
        UniqueConstraint("effect_id", "position", name="uq_effect_steps_effect_position"),
        CheckConstraint("position >= 0", name="ck_effect_steps_position"),
        CheckConstraint(
            "brightness IS NULL OR (brightness >= 0 AND brightness <= 100)",
            name="ck_effect_steps_brightness",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_effect_steps_duration_ms",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    effect_id: UUID = Field(foreign_key="effects.id", ondelete="CASCADE", index=True)

    position: int = Field(ge=0)
    color_hex: str = Field(max_length=7)

    brightness: Optional[int] = Field(default=None, ge=0, le=100)  # noqa: UP045
    duration_ms: Optional[int] = Field(default=None, ge=0)  # noqa: UP045
    easing: Optional[str] = Field(default=None, max_length=30)  # noqa: UP045

    effect: "EffectRecord" = Relationship(back_populates="steps")
