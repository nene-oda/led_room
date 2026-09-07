"""Endpoint `/ws`: comandos de baja latencia y difusion del estado.

Reglas del contrato (README 17, NEXT_STEPS 4.4):

* El **primer** mensaje tras aceptar la conexion es `state.snapshot`, y va SOLO
  a esa conexion: sin el, un cliente recien conectado no sabe en que estado esta
  la habitacion hasta que alguien toca algo.
* Un mensaje invalido devuelve el frame `error` y **no** cierra el socket: un
  arrastre del selector de color no debe tirar la sesion.
* Todo cambio aceptado se difunde a **todos** los clientes, incluido el emisor.
  Es lo que mantiene la coherencia cuando el limitador recorta un comando o el
  hardware lo rechaza: el cliente optimista se corrige solo.

**Este canal no persiste nada.** El estado deseado se escribe en la base ante
intencion del usuario, jamas por fotograma ni durante un arrastre (NEXT_STEPS
A3), y por el socket viaja justamente el arrastre. La frontera que si delimita
una intencion es una peticion HTTP, asi que la persistencia vive en
`api/lights.py`: el cliente cierra el gesto con un `PUT /api/v1/lights/color` (o
manda por REST el encendido y el brillo, que no son de baja latencia) y eso es
lo que sobrevive a un reinicio.

Como en las rutas HTTP, aqui no hay ninguna regla de negocio: se decodifica, se
delega en la capa de aplicacion y se traduce el resultado.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect

from backend.app.api.deps import resources_of
from backend.app.application.light_service import LightService
from backend.app.application.ports import EventPublisher
from backend.app.application.state_store import StateStore
from backend.app.application.throttle import LightThrottles
from backend.app.domain.events import StateSnapshot
from backend.app.domain.lighting import RGBColor
from backend.app.websocket.events import (
    ClientCommand,
    SetBrightness,
    SetColor,
    SetPower,
    decode_command,
    to_error_event,
)
from backend.app.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


def reporting_color_applier(
    light: LightService,
    publisher: EventPublisher,
    store: StateStore,
) -> Callable[[RGBColor], Awaitable[None]]:
    """Envuelve `set_color` para que un fallo del arrastre no muera en el log.

    El limitador aplica el color desde una tarea de fondo: cuando esa escritura
    falla ya no queda nadie a quien devolverle la excepcion, y el usuario veria
    su gesto desaparecer sin explicacion. Se compone aqui, como sugiere el propio
    limitador, en vez de añadirle un gancho de notificacion.

    La difusion alcanza a todos los clientes porque el limitador coalesce los
    valores de todos: no hay forma de saber cual de ellos envio el que fallo.
    """
    return _reporting_applier(light.set_color, publisher, store)


def reporting_brightness_applier(
    light: LightService,
    publisher: EventPublisher,
    store: StateStore,
) -> Callable[[int], Awaitable[None]]:
    """Lo mismo para el arrastre del deslizador de brillo."""
    return _reporting_applier(light.set_brightness, publisher, store)


def _reporting_applier[T](
    apply: Callable[[T], Awaitable[object]],
    publisher: EventPublisher,
    store: StateStore,
) -> Callable[[T], Awaitable[None]]:
    async def report(value: T) -> None:
        try:
            await apply(value)
        except Exception as error:
            await publisher.publish(to_error_event(error), (await store.snapshot()).version)

    return report


async def websocket_endpoint(websocket: WebSocket) -> None:
    resources = resources_of(websocket.app)
    manager = resources.connections
    store = resources.store

    await manager.accept(websocket)
    try:
        # Alta y snapshot bajo el MISMO cerrojo que usan las difusiones: entre
        # dar de alta el socket y encolarle su estado no puede colarse ningun
        # evento, o el cliente aplicaria el cambio y despues el estado viejo que
        # lo contradice, quedandose desincronizado para siempre. Ninguna de las
        # dos operaciones cede el control, asi que el cerrojo global no queda
        # retenido por la red de este cliente.
        async with store.hold() as state:
            manager.register(websocket)
            await manager.send(websocket, StateSnapshot(state=state), state.version)

        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            try:
                command = decode_command(_text_of(message))
                await _dispatch(command, light=resources.light, throttles=resources.throttles)
            except Exception as error:
                # Solo al emisor: el resto de clientes no tiene nada que ver con
                # un comando que uno de ellos escribio mal.
                await _report(manager, websocket, store, error)
    except WebSocketDisconnect:
        logger.debug("Cliente WebSocket desconectado")
    finally:
        manager.disconnect(websocket)


async def _report(
    manager: ConnectionManager,
    websocket: WebSocket,
    store: StateStore,
    error: Exception,
) -> None:
    """Frame `error` al emisor, sellado con la version vigente.

    El error no cambia el estado, asi que repite la ultima version: es lo que le
    dice al cliente que no se perdio nada.
    """
    await manager.send(websocket, to_error_event(error), (await store.snapshot()).version)


def _text_of(message: Mapping[str, Any]) -> str:
    """Extrae el texto de un mensaje ASGI.

    Se usa `receive()` en vez de `receive_text()` para que un frame binario sea
    un `422 invalid_payload` explicito y no un fallo interno.
    """
    text = message.get("text")
    if not isinstance(text, str):
        raise ValueError("Solo se aceptan mensajes de texto con un objeto JSON.")
    return text


async def _dispatch(
    command: ClientCommand,
    *,
    light: LightService,
    throttles: LightThrottles,
) -> None:
    """Color y brillo son arrastres; el encendido es una intencion puntual.

    Los dos deslizadores pasan por su propio limitador -- un deslizador de brillo
    genera igual de facil 200 eventos por segundo que el selector de color, y sin
    limitar serian 200 escrituras BLE serializadas -- y son independientes entre
    si: mover el brillo no invalida el color pendiente, porque son campos
    distintos del estado.

    El encendido si cancela los dos: un color o un brillo pendiente aplicado
    despues de un apagado volveria a encender la tira.
    """
    match command:
        case SetColor(color=color):
            await throttles.color.submit(color)
        case SetBrightness(value=brightness):
            await throttles.brightness.submit(brightness)
        case SetPower(value=value):
            await throttles.cancel_all()
            await light.set_power(value)
