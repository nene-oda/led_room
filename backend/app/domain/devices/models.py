"""Modelos de dominio de dispositivos (README 7)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DeviceType(StrEnum):
    """Familias de hardware soportadas o previstas.

    `NULL` es el dispositivo en memoria que permite operar sin hardware.
    Las demas se añaden cuando exista un adaptador real detras.
    """

    NULL = "null"
    LOTUS_LANTERN = "lotus_lantern"


class DeviceCapabilities(BaseModel):
    """Que sabe hacer un dispositivo concreto.

    Permite soportar hardware distinto sin cambiar la interfaz. Las claves van
    en snake_case en todo el intercambio de datos (design.md D4).
    """

    model_config = ConfigDict(frozen=True)

    rgb: bool
    brightness: bool
    effects: bool
    addressable: bool
    segments: bool
    white_channel: bool


#: Capacidades del hardware soportado hoy: toda la tira muestra un unico color a
#: la vez, asi que las "mezclas" son transiciones temporales (README 2).
SINGLE_COLOR_STRIP = DeviceCapabilities(
    rgb=True,
    brightness=True,
    effects=True,
    addressable=False,
    segments=False,
    white_channel=False,
)


class Device(BaseModel):
    """Un controlador fisico conocido por el sistema."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    address: str
    type: DeviceType
    connected: bool
    capabilities: DeviceCapabilities
