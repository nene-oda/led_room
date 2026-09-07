"""Errores de la capa de aplicacion y su traduccion a la frontera (NEXT_STEPS A6).

Este modulo NO importa FastAPI: define la traduccion **conceptual**
(excepcion -> codigo de estado + codigo estable + mensaje publicable) y la
oleada 3B la convierte en `@app.exception_handler` y en el frame `error` del
WebSocket. Asi la politica de errores vive en un solo sitio y REST y WS no
pueden divergir.

Dos decisiones que no son evidentes:

* **Una escritura colgada llega como `DeviceError`, no como `TimeoutError`**:
  `SerializedLightDevice` ya traduce el timeout en la frontera del transporte, y
  `DeviceService.scan` hace lo mismo con el escaneo. Ninguna capa superior tiene
  que conocer `asyncio.TimeoutError`.
* **`DeviceMappingError` cae en el caso por defecto (500) y eso es correcto**:
  no hereda de `ValueError` justamente para no confundirse con un rango
  invalido del cliente. Una fila corrupta es un fallo del servidor, no una
  peticion mal formada. Por eso este modulo no lo importa: la capa de
  aplicacion no debe conocer los tipos de infraestructura, y no le hace falta.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from backend.app.domain.devices.ports import (
    DeviceCapabilityError,
    DeviceError,
    DeviceNotConnectedError,
    DeviceUnavailableError,
)


class ApplicationError(Exception):
    """Fallo de un caso de uso. No es un fallo del dispositivo ni del dominio."""


class DeviceNotFoundError(ApplicationError):
    """El identificador no corresponde a ningun dispositivo registrado."""


class EffectNotFoundError(ApplicationError):
    """El identificador no corresponde a ningun efecto guardado.

    Tipo propio y no una reutilizacion de `DeviceNotFoundError`: el codigo que
    ve el cliente es contrato con el frontend, y "no existe el efecto" y "no
    existe el dispositivo" llevan a la UI a pantallas distintas.
    """


class SceneNotFoundError(ApplicationError):
    """El identificador no corresponde a ninguna escena guardada.

    Tipo propio por el mismo motivo que `EffectNotFoundError`: el codigo que ve
    el cliente es contrato con el frontend, y "no existe la escena" lleva a la UI
    a una pantalla distinta que "no existe el efecto".
    """


class ProfileNotFoundError(ApplicationError):
    """El identificador no corresponde a ningun perfil guardado."""


class EffectInUseError(ApplicationError):
    """Alguna escena referencia el efecto que se intenta borrar.

    Lo lanza el **repositorio**, que es el unico que puede saberlo: la regla la
    hace cumplir el `RESTRICT` de `scene_targets.effect_id` y solo se manifiesta
    al confirmar. La deteccion vive alli para que este modulo no tenga que
    importar SQLAlchemy -- lo prohibe el guardian de la frontera de aplicacion --
    y lo que sube es esta excepcion, ya traducible.

    Es 409 y no 422: el efecto y la peticion son validos: lo que impide borrarlo
    es el estado del catalogo, y el cliente lo arregla quitando el objetivo de la
    escena (o borrando la escena), no corrigiendo el cuerpo.
    """


class NothingToActivateError(ApplicationError):
    """Lo que se pidio activar esta vacio: no hay nada que reproducir.

    Cubre los dos casos con el mismo codigo porque para el cliente el hecho es
    el mismo -- una escena sin objetivos habilitados y un perfil sin escenas
    llevan a la misma pantalla, "termina de configurarlo" -- y el mensaje ya
    distingue cual de los dos fue.
    """


class DeviceBusyError(ApplicationError):
    """Hay otro dispositivo conectado ocupando el unico enlace del proceso.

    El backend construye UN adaptador (`build_light_device`) y mantiene UNA
    conexion. Conectar un segundo dispositivo sin soltar el primero dejaria el
    estado global describiendo un enlace que ya no existe.
    """


class ErrorCode(StrEnum):
    """Codigo estable que ven el cliente HTTP y el frame `error` del WebSocket.

    Es contrato con el frontend: la UI decide que mensaje mostrar a partir del
    codigo, nunca parseando el texto.
    """

    DEVICE_NOT_FOUND = "device_not_found"
    EFFECT_NOT_FOUND = "effect_not_found"
    SCENE_NOT_FOUND = "scene_not_found"
    PROFILE_NOT_FOUND = "profile_not_found"
    EFFECT_IN_USE = "effect_in_use"
    NOTHING_TO_ACTIVATE = "nothing_to_activate"
    DEVICE_NOT_CONNECTED = "device_not_connected"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    DEVICE_BUSY = "device_busy"
    DEVICE_UNAVAILABLE = "device_unavailable"
    INVALID_PAYLOAD = "invalid_payload"
    DEVICE_WRITE_FAILED = "device_write_failed"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class ErrorTranslation:
    """Como se le cuenta un fallo al cliente."""

    status_code: int
    code: ErrorCode
    message: str


#: Mensaje unico de los 500. La excepcion real se registra en el log y **nunca**
#: se devuelve: un `str(error)` de un fallo interno filtra rutas, SQL o detalles
#: del transporte.
INTERNAL_MESSAGE: Final = "Error interno del servidor."

#: Orden significativo: las subclases van antes que `DeviceError`, que es la
#: base de las tres. La primera coincidencia gana.
_TRANSLATIONS: Final[tuple[tuple[type[BaseException], int, ErrorCode], ...]] = (
    (DeviceNotFoundError, 404, ErrorCode.DEVICE_NOT_FOUND),
    (EffectNotFoundError, 404, ErrorCode.EFFECT_NOT_FOUND),
    (SceneNotFoundError, 404, ErrorCode.SCENE_NOT_FOUND),
    (ProfileNotFoundError, 404, ErrorCode.PROFILE_NOT_FOUND),
    (NothingToActivateError, 409, ErrorCode.NOTHING_TO_ACTIVATE),
    (EffectInUseError, 409, ErrorCode.EFFECT_IN_USE),
    (DeviceBusyError, 409, ErrorCode.DEVICE_BUSY),
    (DeviceNotConnectedError, 409, ErrorCode.DEVICE_NOT_CONNECTED),
    (DeviceCapabilityError, 409, ErrorCode.UNSUPPORTED_CAPABILITY),
    # No hay medio con el que operar: radio ausente, apagada o denegada. Va
    # ANTES que `DeviceError` porque hereda de el, y es 503 y no 502 porque el
    # fallo no esta en el dispositivo sino en el host: reintentar sin tocar nada
    # volvera a fallar, y lo que hay que arreglar esta al alcance del usuario.
    (DeviceUnavailableError, 503, ErrorCode.DEVICE_UNAVAILABLE),
    # Transporte: escritura fallida, enlace caido o timeout ya traducido.
    (DeviceError, 502, ErrorCode.DEVICE_WRITE_FAILED),
    # Incluye `pydantic.ValidationError`, que hereda de `ValueError`: un rango
    # fuera de 0-255 o 0-100 detectado al construir el modelo de dominio.
    (ValueError, 422, ErrorCode.INVALID_PAYLOAD),
)


#: Primer elemento del `loc` de FastAPI: de que parte de la peticion vino el
#: fallo. Los `ValidationError` de Pydantic que produce el WebSocket no lo
#: llevan, y por eso se recorta solo cuando esta.
_REQUEST_LOCATIONS: Final = frozenset({"body", "query", "path", "header", "cookie"})

#: Mensaje cuando la validacion no dice nada aprovechable.
_INVALID_PAYLOAD_MESSAGE: Final = "Peticion invalida."


def summarize_validation_error(error: BaseException) -> str | None:
    """Resume un fallo de validacion; `None` si la excepcion no es uno.

    Sirve para las dos: el `ValidationError` de Pydantic que produce el
    WebSocket al validar el payload y el `RequestValidationError` de FastAPI que
    produce el cuerpo de una peticion REST. Se reconocen por la forma (`errors()`)
    y no por el tipo porque este modulo no puede importar FastAPI sin invertir
    la direccion de las dependencias -- y el resumen es identico para ambas.

    Sin esto, el frame `error` del WebSocket volcaba el `str()` crudo de
    Pydantic: multilinea y con la URL de la version, mientras que por REST salia
    un `"r: Input should be less than or equal to 255"`. La politica de errores
    dice ser la misma para los dos transportes; esta funcion es lo que lo hace
    cierto.
    """
    details = _validation_details(error)
    if details is None:
        return None

    parts: list[str] = []
    for detail in details:
        message = detail.get("msg")
        if not isinstance(message, str):
            continue
        location = _location(detail.get("loc"))
        parts.append(f"{location}: {message}" if location else message)

    return "; ".join(parts) if parts else _INVALID_PAYLOAD_MESSAGE


def _validation_details(error: BaseException) -> Sequence[Mapping[str, Any]] | None:
    errors = getattr(error, "errors", None)
    if not callable(errors):
        return None

    try:
        details = errors()
    except Exception:  # pragma: no cover - defensivo: `errors()` de otra cosa
        return None

    if not isinstance(details, Sequence) or not all(
        isinstance(detail, Mapping) for detail in details
    ):
        return None
    return details


def _location(loc: object) -> str:
    if not isinstance(loc, Sequence) or isinstance(loc, str):
        return ""

    parts = list(loc)
    if parts and parts[0] in _REQUEST_LOCATIONS:
        parts = parts[1:]
    return ".".join(str(part) for part in parts)


def translate_error(error: BaseException) -> ErrorTranslation:
    """Traduce una excepcion a lo que se puede publicar sin filtrar nada.

    Fuente UNICA de la politica: REST y WebSocket la comparten entera, resumen
    de validacion incluido.
    """
    summary = summarize_validation_error(error)

    for error_type, status_code, code in _TRANSLATIONS:
        if isinstance(error, error_type):
            message = summary if code is ErrorCode.INVALID_PAYLOAD and summary else str(error)
            return ErrorTranslation(status_code=status_code, code=code, message=message)

    if summary is not None:
        # `RequestValidationError` de FastAPI no hereda de `ValueError`, pero es
        # el mismo fallo del cliente: sin esta rama, el mismo rango invalido
        # responderia 422 por WebSocket y 500 por REST.
        return ErrorTranslation(status_code=422, code=ErrorCode.INVALID_PAYLOAD, message=summary)

    return ErrorTranslation(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message=INTERNAL_MESSAGE,
    )
