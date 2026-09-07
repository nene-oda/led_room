"""Implementaciones SQLModel de los puertos de repositorio del dominio.

Dispositivos (Fases 1-4), efectos (Fase 5), escenas (Fase 6) y perfiles
(Fase 7). `schedules` sigue sin caso de uso propietario y, por la regla de
ARCHITECTURE 7.5, tampoco tiene repositorio ni mapper.
"""

from __future__ import annotations

from backend.app.infrastructure.persistence.repositories.device_repository import (
    SQLModelDeviceRepository,
)
from backend.app.infrastructure.persistence.repositories.effect_repository import (
    SQLModelEffectRepository,
)
from backend.app.infrastructure.persistence.repositories.profile_repository import (
    SQLModelProfileRepository,
)
from backend.app.infrastructure.persistence.repositories.scene_repository import (
    SQLModelSceneRepository,
)

__all__ = [
    "SQLModelDeviceRepository",
    "SQLModelEffectRepository",
    "SQLModelProfileRepository",
    "SQLModelSceneRepository",
]
