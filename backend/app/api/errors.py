"""Politica de errores en la frontera HTTP (NEXT_STEPS A6).

Este modulo **no decide** que codigo de estado corresponde a cada fallo, ni como
se redacta el mensaje: eso lo decide `application/errors.translate_error`, que es
la unica fuente y la que comparten REST y WebSocket. Aqui solo se convierte esa
traduccion en una respuesta de FastAPI. Cuando el resumen de los fallos de
validacion vivia aqui, el frame `error` del socket volcaba el `str()` crudo de
Pydantic mientras REST devolvia un resumen legible.

Cuerpo uniforme, sin trazas:

```json
{"detail": {"code": "device_not_connected", "message": "..."}}
```

La traza va al log del servidor y **nunca** al cliente: un `str(error)` de un
fallo interno filtra rutas, SQL o detalles del transporte. Por eso los 500
responden siempre el mismo mensaje generico.

Los 404 de rutas inexistentes (`/api/v1/typo`) se dejan con el cuerpo por
defecto de FastAPI a proposito: no los produce este codigo, sino el enrutador, y
darles un `code` obligaria a inventar un valor que no esta en `ErrorCode`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.application.errors import (
    ApplicationError,
    ErrorCode,
    translate_error,
)
from backend.app.domain.devices.ports import DeviceError

logger = logging.getLogger(__name__)


def error_body(code: ErrorCode, message: str) -> dict[str, Any]:
    """Cuerpo unico de error. Lo usan todos los handlers de este modulo."""
    return {"detail": {"code": code.value, "message": message}}


async def handle_known_error(request: Request, exc: Exception) -> JSONResponse:
    """Traduce cualquier excepcion conocida (y las desconocidas, a 500)."""
    translation = translate_error(exc)

    if translation.status_code >= 500:
        # La excepcion completa va SOLO aqui.
        logger.error(
            "Fallo interno atendiendo %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
    else:
        logger.info(
            "%s %s -> %d (%s)",
            request.method,
            request.url.path,
            translation.status_code,
            translation.code.value,
        )

    return JSONResponse(
        status_code=translation.status_code,
        content=error_body(translation.code, translation.message),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Da de alta la politica de errores en la aplicacion.

    Starlette resuelve el handler recorriendo el MRO de la excepcion, asi que
    registrar las tres bases cubre a todas sus subclases: no hay que enumerar
    `DeviceNotFoundError`, `DeviceBusyError` ni las demas.
    """
    for error_type in (ApplicationError, DeviceError, ValueError):
        app.add_exception_handler(error_type, handle_known_error)

    # `RequestValidationError` no hereda de `ValueError`, asi que hay que
    # nombrarlo; el handler es el MISMO porque `translate_error` ya sabe
    # resumirlo. Registrarlo sustituye al handler por defecto de FastAPI, que
    # responde con otra forma de cuerpo.
    app.add_exception_handler(RequestValidationError, handle_known_error)

    # Ultimo recurso: lo atiende `ServerErrorMiddleware`, que ademas re-lanza
    # para que el servidor lo registre. El cliente solo ve el 500 generico.
    app.add_exception_handler(Exception, handle_known_error)
