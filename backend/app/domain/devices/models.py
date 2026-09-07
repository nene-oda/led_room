"""Modelos de dominio de dispositivos (README 7, NEXT_STEPS A1).

Tres tipos distintos que antes estaban mezclados en uno solo:

* `Device` — **identidad persistida**. Lo que sobrevive a un reinicio.
* `DeviceStatus` — **estado efimero**. Vive en memoria y NUNCA se persiste.
* `DiscoveredDevice` — resultado de un escaneo: aun no es un `Device`, porque
  todavia no tiene identidad en la base (`GET /devices/scan`, README 16).
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceType(StrEnum):
    """Familias de hardware soportadas o previstas.

    Vocabulario UNICO de adaptador en todo el proyecto: la configuracion
    (`LED_ROOM_DEVICE_ADAPTER`), la columna `devices.adapter_type` y la futura
    tabla de adaptadores se refieren a estos mismos valores. Tener tres listas
    del mismo concepto era el fallo que cierra NEXT_STEPS A1.

    `NULL` es el dispositivo en memoria que permite operar sin hardware. Las
    demas se añaden cuando exista un adaptador real detras.
    """

    NULL = "null"
    LOTUS_LANTERN = "lotus_lantern"


class DeviceCapabilities(BaseModel):
    """Que sabe hacer un dispositivo concreto.

    Permite soportar hardware distinto sin cambiar la interfaz: la UI decide que
    renderizar a partir de esto, nunca del `adapter_type` ni de nombres BLE.
    Las claves van en snake_case en todo el intercambio (ARCHITECTURE 3.4).

    Los nombres NO coinciden con los de `DeviceCapabilitiesRecord`
    (`supports_rgb` ↔ `rgb`): el mapeo vive en persistencia y esta justificado en
    ARCHITECTURE 5.4. `backend/tests/test_architecture.py` comprueba que ambos
    conjuntos siguen cubriendose.
    """

    model_config = ConfigDict(frozen=True)

    rgb: bool
    brightness: bool
    effects: bool
    addressable: bool
    segments: bool
    white_channel: bool
    music_mode: bool


#: Capacidades del hardware soportado hoy: toda la tira muestra un unico color a
#: la vez, asi que las "mezclas" son transiciones temporales (README 2).
#: `music_mode` es False a proposito: que el controlador tenga microfono no
#: prueba que el protocolo BLE permita activarlo. Eso lo decide la Fase 0
#: (ARCHITECTURE 5.4).
SINGLE_COLOR_STRIP = DeviceCapabilities(
    rgb=True,
    brightness=True,
    effects=True,
    addressable=False,
    segments=False,
    white_channel=False,
    music_mode=False,
)


class Device(BaseModel):
    """Un controlador conocido por el sistema. Solo identidad, sin estado vivo.

    `connected` NO esta aqui: mezclar identidad persistida con estado efimero
    obliga a escribir en la base cada vez que se cae el enlace BLE. Lo efimero
    va en `DeviceStatus`.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    adapter_type: DeviceType

    #: Identidad de transporte, deliberadamente neutral: una MAC en Linux, un
    #: GUID de WinRT en Windows, una IP o URL para un futuro adaptador WLED. Se
    #: obtiene SIEMPRE de un escaneo, jamas escrita a mano en el codigo.
    #: `None` mientras el dispositivo no se haya emparejado con un resultado real.
    address: str | None = None

    #: Coinciden con los valores por defecto de `DeviceRecord`.
    enabled: bool = True
    auto_connect: bool = True

    capabilities: DeviceCapabilities


class DeviceStatus(BaseModel):
    """Estado efimero de un dispositivo. Nunca se persiste.

    Se reconstruye en cada arranque a partir de la realidad del enlace. Viaja en
    `GlobalState` y en los eventos `device.connected` / `device.disconnected`.
    """

    model_config = ConfigDict(frozen=True)

    device_id: UUID
    connected: bool
    rssi: int | None = None

    #: Codigo estable del ultimo fallo de enlace, nunca su texto: viaja a todos
    #: los clientes en `GET /api/v1/state` y en `state.snapshot`.
    last_error: str | None = None


class DeviceTarget(BaseModel):
    """A que dispositivo concreto se abre el enlace.

    Existe porque `LightDevicePort.connect()` no llevaba destino: la factoria
    construye UN adaptador desde la configuracion y `Device.address` se
    persistia, se indexaba con UNIQUE y se devolvia por la API, pero jamas
    llegaba al adaptador. Con un solo controlador el fallo es invisible; con dos
    tiras registradas, conectar la del salon y la del dormitorio ejecutaria
    exactamente el mismo codigo.

    `address` es la MISMA identidad de transporte neutral que `Device.address`:
    una MAC en Linux, un GUID de WinRT en Windows, una IP para un futuro
    adaptador WLED. Es un tipo aparte, y no `Device`, por segregacion de
    interfaces: un adaptador no necesita el nombre visible, el `enabled` ni las
    capacidades persistidas para abrir un enlace.
    """

    model_config = ConfigDict(frozen=True)

    address: str = Field(min_length=1)


class DiscoveredDevice(BaseModel):
    """Un dispositivo visto en un escaneo y todavia no registrado.

    Es exactamente lo que devuelve `GET /devices/scan` (README 16): sin `id`,
    porque aun no existe en la base. Registrarlo con `POST /devices` es lo que
    lo convierte en un `Device`.
    """

    model_config = ConfigDict(frozen=True)

    #: Muchos controladores de esta clase se anuncian sin nombre.
    name: str | None = None
    address: str
    rssi: int | None = None
