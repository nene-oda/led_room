"""Traduccion entre los eventos de dominio y los frames del WebSocket.

El envoltorio es el de ARCHITECTURE 3.6. Del cliente al servidor:

```json
{ "type": "<nombre>", "payload": { } }
```

Y del servidor al cliente, con la version del estado global que produjo el
frame:

```json
{ "type": "<nombre>", "version": 12, "payload": { } }
```

`version` va en TODOS los frames servidor -> cliente, tambien en `error` y en
`state.snapshot`. Es lo unico que permite al cliente detectar un hueco: hay dos
por diseño (una conexion fallida gasta version sin publicar evento, y la cola de
salida de un cliente lento descarta frames), y sin este numero ninguno era
observable. Ante un salto, el cliente rehidrata con `GET /api/v1/state`.

Aqui vive **todo** lo que el dominio deliberadamente no decide: que el color
viaja como `#RRGGBB` en los eventos y como `{r,g,b}` en los comandos, que un
`UUID` se serializa como cadena y que el payload de `state.snapshot` es
exactamente el cuerpo de `GET /api/v1/state`.

Los comandos entrantes se validan con los **mismos** modelos que los cuerpos
REST (`api/schemas/lights.py`): un rango 0-255 no puede significar una cosa por
HTTP y otra por socket. Por eso este modulo importa `api.schemas`, que es el
contrato del cable y no una capa superior.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from backend.app.api.schemas.lights import BrightnessRequest, ColorRequest, PowerRequest
from backend.app.api.schemas.state import GlobalStateRead
from backend.app.application.errors import translate_error
from backend.app.domain.events import DomainEvent, ErrorOccurred, LightColorChanged, StateSnapshot
from backend.app.domain.lighting import RGBColor

logger = logging.getLogger(__name__)


class CommandType(StrEnum):
    """Comandos del cliente al servidor: imperativo y sin sufijo (README 17)."""

    LIGHT_POWER = "light.power"
    LIGHT_COLOR = "light.color"
    LIGHT_BRIGHTNESS = "light.brightness"


@dataclass(frozen=True, slots=True)
class SetPower:
    """`light.power`."""

    value: bool


@dataclass(frozen=True, slots=True)
class SetColor:
    """`light.color`. Es el unico comando de arrastre: pasa por el limitador."""

    color: RGBColor


@dataclass(frozen=True, slots=True)
class SetBrightness:
    """`light.brightness`."""

    value: int


#: Un comando ya validado. El endpoint decide que hacer con cada uno sin volver
#: a mirar cadenas ni diccionarios.
ClientCommand = SetPower | SetColor | SetBrightness

_Parser = Callable[[Mapping[str, Any]], ClientCommand]

#: Tabla explicita en vez de `match`: garantiza que cada miembro de
#: `CommandType` tenga exactamente un constructor, y un test lo comprueba.
_PARSERS: Final[Mapping[CommandType, _Parser]] = {
    CommandType.LIGHT_POWER: lambda payload: SetPower(PowerRequest.model_validate(payload).on),
    CommandType.LIGHT_COLOR: lambda payload: SetColor(
        ColorRequest.model_validate(payload).to_domain()
    ),
    CommandType.LIGHT_BRIGHTNESS: lambda payload: SetBrightness(
        BrightnessRequest.model_validate(payload).brightness
    ),
}


def decode_command(raw: str) -> ClientCommand:
    """Valida un mensaje del cliente.

    Lanza `ValueError` (incluida `ValidationError`, que lo es) ante cualquier
    problema: la politica de errores ya lo traduce a `invalid_payload`. Quien
    llama responde con el frame `error` y **no** cierra el socket: un arrastre
    del selector de color no debe tirar la sesion.
    """
    try:
        message = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"El mensaje no es JSON valido: {error.msg}.") from error

    if not isinstance(message, dict):
        raise ValueError("Se esperaba un objeto JSON con las claves 'type' y 'payload'.")

    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("La clave 'payload' debe ser un objeto JSON.")

    return _PARSERS[_command_type(message.get("type"))](payload)


def _command_type(raw_type: object) -> CommandType:
    """Resuelve el nombre del comando sin presuponer que sea siquiera una cadena."""
    for member in CommandType:
        if member.value == raw_type:
            return member

    known = ", ".join(member.value for member in CommandType)
    raise ValueError(f"Tipo de mensaje desconocido: {raw_type!r}. Se esperaba uno de: {known}.")


def encode_event(event: DomainEvent, version: int) -> str:
    """Serializa un evento de dominio a texto, listo para difundir.

    Se llama UNA vez por difusion: el gestor de conexiones reparte la misma
    cadena a todos los clientes en vez de repetir el volcado por cada uno.

    `version` es la del estado global en el momento de publicar, y va en el
    sobre y no en el payload: los payloads son el contrato congelado de cada
    evento (ARCHITECTURE 3.6) y meter ahi un campo de transporte obligaria a
    repetirlo en cada uno.
    """
    return json.dumps({"type": event.type.value, "version": version, "payload": _payload(event)})


def _payload(event: DomainEvent) -> dict[str, Any]:
    if isinstance(event, LightColorChanged):
        # El evento de dominio lleva `RGBColor`; el cable, la cadena canonica.
        return {"color": event.color.to_hex()}

    if isinstance(event, StateSnapshot):
        # Misma forma exacta que `GET /api/v1/state`.
        return GlobalStateRead.from_domain(event.state).model_dump(mode="json")

    # `mode="json"` convierte los UUID en cadenas. `type` ya va en el envoltorio.
    return event.model_dump(mode="json", exclude={"type"})


def to_error_event(error: BaseException) -> ErrorOccurred:
    """Convierte una excepcion en el frame `error`, con la MISMA politica que HTTP.

    Registrar el fallo interno aqui (y no en cada llamante) es lo que garantiza
    que la traza quede en el log y no viaje al cliente.
    """
    translation = translate_error(error)

    if translation.status_code >= 500:
        logger.error("Fallo interno atendiendo un comando de WebSocket", exc_info=error)

    return ErrorOccurred(code=translation.code.value, message=translation.message)
