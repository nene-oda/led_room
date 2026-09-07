"""Estado global autoritativo (README 31, NEXT_STEPS A4).

```text
Fuente de verdad   = este objeto, en memoria del proceso backend
SQLite             = cache de arranque (ultimo estado deseado; no se lee en caliente)
Adaptador/hardware = sumidero (no se le consulta el estado)
Clientes (React)   = replicas; pueden ser optimistas, pero el servidor gana siempre
```

`GlobalState` es **inmutable**. El unico titular mutable sera
`application/state_store.py`, que produce la version siguiente con
`state.model_copy(update={"light": ..., "version": state.version + 1})` y solo
despues publica el evento correspondiente. Que `version` sea estrictamente
creciente es lo que permite a un cliente detectar que se perdio eventos y pedir
un `state.snapshot` nuevo.

Es tambien el cuerpo de `GET /api/v1/state` y el payload de `state.snapshot`:
una sola forma para hidratar por REST y por WebSocket.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.devices.models import DeviceStatus
from backend.app.domain.lighting import LightState


class EffectStatus(BaseModel):
    """Efecto en curso. Se rellena en la Fase 5.

    `running` se conserva porque la forma del README 31 lo incluye; la ausencia
    de efecto se representa con `GlobalState.effect = None`.
    """

    model_config = ConfigDict(frozen=True)

    running: bool
    id: UUID


class SceneStatus(BaseModel):
    """Escena activa. Se rellena en la Fase 6."""

    model_config = ConfigDict(frozen=True)

    id: UUID


class GlobalState(BaseModel):
    """Lo que el servidor conserva y difunde a todos los clientes."""

    model_config = ConfigDict(frozen=True)

    #: Monotono. 0 es el estado inicial, aun sin ninguna mutacion aplicada.
    version: int = Field(default=0, ge=0)

    #: `None` mientras no haya ningun dispositivo seleccionado.
    device: DeviceStatus | None = None

    light: LightState = Field(default_factory=LightState)

    effect: EffectStatus | None = None
    scene: SceneStatus | None = None
