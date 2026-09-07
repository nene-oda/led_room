"""Eventos de dominio (ARCHITECTURE 3.6, NEXT_STEPS A4).

Son tipos de DOMINIO, no mensajes de WebSocket. El envoltorio
`{"type": ..., "payload": {...}}` y la serializacion del color (`#RRGGBB` en el
estado, `{r,g,b}` en las mutaciones, ARCHITECTURE 3.2) son responsabilidad de
`websocket/events.py`. Por eso aqui el color viaja como `RGBColor` y no como
cadena: si el dominio decidiera el formato del cable, cambiar el cable obligaria
a tocar el dominio.

La capa de aplicacion publica estos eventos a traves de
`application.ports.EventPublisher`, nunca contra el gestor de WebSocket.

**Nombres congelados** (ARCHITECTURE 3.6, README 17): `device.connected`,
`device.disconnected`, `light.power.changed`, `light.color.changed`,
`light.brightness.changed`, `effect.started`, `effect.stopped`,
`scene.activated`.

**Ampliaciones pendientes de reflejar en ARCHITECTURE 3.6** — la lista congelada
solo contiene eventos de exito y ninguno entrega el estado completo:

* `state.snapshot` — primer mensaje tras aceptar la conexion, y cuerpo de
  `GET /api/v1/state`. Sin el, un cliente recien conectado no sabe en que
  estado esta la habitacion hasta que alguien toca algo.
* `error` — `{code, message}`. Sin el, un comando invalido por WebSocket falla
  en silencio, que es el peor modo posible para un control de arrastre. El
  catalogo de `code` lo fija la politica de errores (NEXT_STEPS A6); aqui se
  deja como cadena para no congelarlo antes de tiempo.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.domain.lighting import Percent, RGBColor
from backend.app.domain.state import GlobalState


class EventType(StrEnum):
    """Nombre de cada evento. Unica definicion de las cadenas del contrato."""

    DEVICE_CONNECTED = "device.connected"
    DEVICE_DISCONNECTED = "device.disconnected"
    LIGHT_POWER_CHANGED = "light.power.changed"
    LIGHT_COLOR_CHANGED = "light.color.changed"
    LIGHT_BRIGHTNESS_CHANGED = "light.brightness.changed"
    EFFECT_STARTED = "effect.started"
    EFFECT_STOPPED = "effect.stopped"
    SCENE_ACTIVATED = "scene.activated"

    # Ampliaciones (ver docstring del modulo).
    STATE_SNAPSHOT = "state.snapshot"
    ERROR = "error"


class DomainEvent(BaseModel):
    """Algo que ya ocurrio. Se publica **despues** de que el dispositivo lo acepte.

    Publicar antes de escribir desincroniza a los clientes justo cuando el
    enlace BLE se cae, que es cuando la sincronia importa (NEXT_STEPS A4).
    """

    model_config = ConfigDict(frozen=True)

    type: EventType


class DeviceConnected(DomainEvent):
    type: Literal[EventType.DEVICE_CONNECTED] = EventType.DEVICE_CONNECTED
    device_id: UUID


class DeviceDisconnected(DomainEvent):
    type: Literal[EventType.DEVICE_DISCONNECTED] = EventType.DEVICE_DISCONNECTED
    device_id: UUID


class LightPowerChanged(DomainEvent):
    type: Literal[EventType.LIGHT_POWER_CHANGED] = EventType.LIGHT_POWER_CHANGED
    power: bool


class LightColorChanged(DomainEvent):
    type: Literal[EventType.LIGHT_COLOR_CHANGED] = EventType.LIGHT_COLOR_CHANGED
    color: RGBColor


class LightBrightnessChanged(DomainEvent):
    type: Literal[EventType.LIGHT_BRIGHTNESS_CHANGED] = EventType.LIGHT_BRIGHTNESS_CHANGED
    brightness: Percent


class EffectStarted(DomainEvent):
    type: Literal[EventType.EFFECT_STARTED] = EventType.EFFECT_STARTED
    effect_id: UUID


class EffectStopped(DomainEvent):
    type: Literal[EventType.EFFECT_STOPPED] = EventType.EFFECT_STOPPED
    effect_id: UUID


class SceneActivated(DomainEvent):
    type: Literal[EventType.SCENE_ACTIVATED] = EventType.SCENE_ACTIVATED
    scene_id: UUID


class StateSnapshot(DomainEvent):
    """Estado completo. Hidrata a un cliente nuevo o tras una reconexion."""

    type: Literal[EventType.STATE_SNAPSHOT] = EventType.STATE_SNAPSHOT
    state: GlobalState


class ErrorOccurred(DomainEvent):
    """Un comando fue rechazado. NO cierra la conexion del cliente."""

    type: Literal[EventType.ERROR] = EventType.ERROR
    code: str
    message: str
