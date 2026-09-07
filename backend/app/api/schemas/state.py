"""DTO del estado global: cuerpo de `GET /state` y del frame `state.snapshot`.

Una sola forma para hidratar por REST y por WebSocket (NEXT_STEPS A4). Si un
cliente reconecta y pide el estado por HTTP debe recibir exactamente lo mismo
que recibiria por el socket.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.api.schemas.lights import LightStateRead
from backend.app.domain.devices.models import DeviceStatus
from backend.app.domain.state import EffectStatus, GlobalState, SceneStatus


class DeviceStatusRead(BaseModel):
    """Estado efimero del enlace. Nunca se persiste."""

    device_id: str
    connected: bool
    rssi: int | None = None

    #: **Codigo estable** de `ErrorCode` (p. ej. `"device_write_failed"`), no el
    #: texto del fallo: esto se difunde a todos los clientes y sin autenticacion,
    #: y el mensaje de una biblioteca BLE incluye la direccion del controlador y
    #: rutas de D-Bus. La UI decide que mostrar a partir del codigo, igual que
    #: con los errores de la API; el texto completo queda en el log.
    last_error: str | None = None

    @classmethod
    def from_domain(cls, status: DeviceStatus) -> DeviceStatusRead:
        return cls(
            device_id=str(status.device_id),
            connected=status.connected,
            rssi=status.rssi,
            last_error=status.last_error,
        )


class EffectStatusRead(BaseModel):
    """Efecto en curso. Hoy siempre `null`: el motor llega en la Fase 5."""

    running: bool
    id: str

    @classmethod
    def from_domain(cls, effect: EffectStatus) -> EffectStatusRead:
        return cls(running=effect.running, id=str(effect.id))


class SceneStatusRead(BaseModel):
    """Escena activa. Hoy siempre `null`: las escenas llegan en la Fase 6."""

    id: str

    @classmethod
    def from_domain(cls, scene: SceneStatus) -> SceneStatusRead:
        return cls(id=str(scene.id))


class GlobalStateRead(BaseModel):
    """Lo que el servidor conserva y difunde (README 31)."""

    #: Monotono. Permite a un cliente detectar que se perdio eventos y pedir un
    #: snapshot nuevo en vez de quedarse mostrando un estado viejo.
    version: int = Field(ge=0)

    device: DeviceStatusRead | None = None
    light: LightStateRead
    effect: EffectStatusRead | None = None
    scene: SceneStatusRead | None = None

    @classmethod
    def from_domain(cls, state: GlobalState) -> GlobalStateRead:
        return cls(
            version=state.version,
            device=None if state.device is None else DeviceStatusRead.from_domain(state.device),
            light=LightStateRead.from_domain(state.light),
            effect=None if state.effect is None else EffectStatusRead.from_domain(state.effect),
            scene=None if state.scene is None else SceneStatusRead.from_domain(state.scene),
        )
