"""Modelos persistentes SQLModel.

IMPORTANTE: importar este paquete debe registrar TODAS las tablas en
`SQLModel.metadata`. Alembic y `create_all` solo ven lo que se haya importado
antes de mirar el metadata (LED_ROOM_DATABASE_MODEL 47), y SQLAlchemy no puede
configurar los mappers si falta una clase referenciada por una relacion.
"""

from __future__ import annotations

from backend.app.infrastructure.persistence.models.base import UtcDateTime, utc_now
from backend.app.infrastructure.persistence.models.device import (
    DeviceCapabilitiesRecord,
    DeviceRecord,
    DeviceStateRecord,
)
from backend.app.infrastructure.persistence.models.effect import EffectRecord, EffectStepRecord
from backend.app.infrastructure.persistence.models.profile import ProfileRecord, ProfileSceneRecord
from backend.app.infrastructure.persistence.models.scene import SceneRecord, SceneTargetRecord
from backend.app.infrastructure.persistence.models.schedule import ScheduleRecord

__all__ = [
    "DeviceCapabilitiesRecord",
    "DeviceRecord",
    "DeviceStateRecord",
    "EffectRecord",
    "EffectStepRecord",
    "ProfileRecord",
    "ProfileSceneRecord",
    "SceneRecord",
    "SceneTargetRecord",
    "ScheduleRecord",
    "UtcDateTime",
    "utc_now",
]
