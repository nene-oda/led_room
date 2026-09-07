"""Gestor de conexiones WebSocket. Implementa `EventPublisher` (NEXT_STEPS A4).

Es la unica pieza que conoce a la vez los eventos de dominio y el transporte.
La capa de aplicacion publica contra el **puerto**, nunca contra esta clase: esa
direccion de dependencia es lo que impide que un servicio acabe importando
FastAPI para mandar un mensaje.

No hay singleton de modulo: el gestor se construye en el `lifespan` y se guarda
en `app.state`, de modo que dos aplicaciones creadas en el mismo proceso (los
tests crean muchas) no comparten conexiones.

**Difusion desacoplada de la red.** `publish` y `send` solo ENCOLAN: no esperan
a que ningun cliente acepte el frame y por tanto no ceden el control. Cada
conexion tiene su propia cola acotada y su propia tarea escritora, que es la
unica que toca el socket.

Esto no es una optimizacion: `StateStore` publica **dentro** del cerrojo del
estado global (para que el orden de difusion coincida con el de `version`), asi
que si `publish` esperase a la red, un cliente lento retendria ese cerrojo
durante toda la difusion y frenaria los comandos de todos los demas. Medido:
un socket que no drena costaba 1,01 s por comando, y un cliente meramente lento
(100 ms) bajaba la cadencia efectiva de 20 act./s a ~9 de forma permanente. Con
el motor de efectos de la Fase 5, que publicara por fotograma, cada fotograma se
serializaria contra la red del peor cliente.

Cuando la cola de un cliente se llena se descarta **el frame mas viejo**: son
notificaciones de estado, y el ultimo siempre vale mas que el primero. El hueco
resultante es detectable porque el sobre lleva la `version` (ARCHITECTURE 3.6),
asi que el cliente rehidrata con `GET /api/v1/state`.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field

from starlette.websockets import WebSocket

from backend.app.domain.events import DomainEvent
from backend.app.websocket.events import encode_event

logger = logging.getLogger(__name__)

#: Cuanto se espera a que un cliente acepte UN frame antes de darlo por perdido.
#: Ya no penaliza a nadie mas (la espera ocurre en la tarea escritora de esa
#: conexion), asi que puede ser generoso: solo distingue "va lento" de "el
#: socket esta muerto".
DEFAULT_SEND_TIMEOUT_S = 1.0

#: Frames pendientes que se le toleran a un cliente antes de empezar a descartar
#: los mas viejos. A 20 actualizaciones por segundo son ~1,5 s de margen: cubre
#: un hipo de red sin convertirse en la "cola de valores obsoletos" que el
#: limitador existe para evitar.
DEFAULT_QUEUE_SIZE = 32

#: 1011 = "internal error" en el RFC 6455: el servidor no puede seguir
#: atendiendo a esta conexion concreta.
_SLOW_CLIENT_CLOSE_CODE = 1011


@dataclass(eq=False, slots=True)
class _Connection:
    """Un cliente y su via de salida: cola acotada + una unica tarea escritora."""

    websocket: WebSocket
    queue: asyncio.Queue[str]
    task: asyncio.Task[None] | None = field(default=None)


class ConnectionManager:
    """Alta, baja y difusion. Ninguna de las tres puede lanzar hacia arriba."""

    def __init__(
        self,
        *,
        send_timeout_s: float = DEFAULT_SEND_TIMEOUT_S,
        queue_size: int = DEFAULT_QUEUE_SIZE,
    ) -> None:
        if send_timeout_s <= 0:
            raise ValueError(f"El timeout de envio debe ser positivo; se recibio {send_timeout_s}")
        if queue_size <= 0:
            raise ValueError(f"El tamaño de la cola debe ser positivo; se recibio {queue_size}")

        self._connections: dict[WebSocket, _Connection] = {}
        self._send_timeout_s = send_timeout_s
        self._queue_size = queue_size

    @property
    def count(self) -> int:
        """Conexiones vivas. Util para diagnostico y para los tests."""
        return len(self._connections)

    async def accept(self, websocket: WebSocket) -> None:
        """Completa el handshake. **No** da de alta.

        Esta separado de `register` porque el alta ocurre bajo el cerrojo del
        estado global (`StateStore.hold`), y dentro de ese cerrojo no puede
        haber ninguna espera de red.
        """
        await websocket.accept()

    def register(self, websocket: WebSocket) -> None:
        """Da de alta y arranca su escritora. Idempotente y **sin ceder el control**.

        Que sea sincrona no es un detalle: es lo que permite ejecutarla dentro
        de `StateStore.hold()` sin bloquear a nadie.
        """
        if websocket in self._connections:
            return

        connection = _Connection(websocket, asyncio.Queue(maxsize=self._queue_size))
        self._connections[websocket] = connection
        connection.task = asyncio.create_task(self._writer(connection))

    def disconnect(self, websocket: WebSocket) -> None:
        """Da de baja y detiene su escritora. Idempotente y segura de repetir.

        Los frames que quedaran encolados se descartan: quien llama a esto es el
        endpoint cuando el cliente ya se ha ido.
        """
        connection = self._connections.pop(websocket, None)
        if connection is None or connection.task is None:
            return

        # La propia escritora llama aqui al descartar su conexion; cancelarse a
        # si misma abortaria el cierre ordenado del socket.
        if connection.task is not asyncio.current_task():
            connection.task.cancel()

    async def close_all(self) -> None:
        """Cierre ordenado del `lifespan`: ninguna escritora sobrevive al proceso."""
        for websocket in list(self._connections):
            self.disconnect(websocket)

    async def publish(self, event: DomainEvent, version: int) -> None:
        """Difunde a TODOS los clientes, incluido el que origino el cambio.

        Cumple `EventPublisher`: no lanza pase lo que pase, y **no espera a la
        red**. Un fallo de difusion no puede deshacer un cambio que el hardware
        ya acepto, ni retrasar el siguiente comando.
        """
        if not self._connections:
            return

        # Se serializa UNA vez por difusion, no una por cliente.
        frame = encode_event(event, version)
        for connection in list(self._connections.values()):
            self._enqueue(connection, frame)

    async def send(self, websocket: WebSocket, event: DomainEvent, version: int) -> None:
        """Encola para UNA conexion. Es el snapshot inicial y los frames de `error`.

        `publish` es difusion: usarlo para hidratar a un cliente nuevo mandaria
        su estado a todos los demas.
        """
        connection = self._connections.get(websocket)
        if connection is None:
            return

        self._enqueue(connection, encode_event(event, version))

    def _enqueue(self, connection: _Connection, frame: str) -> None:
        """Encola descartando el frame mas viejo si no cabe. Nunca bloquea."""
        while True:
            try:
                connection.queue.put_nowait(frame)
                return
            except asyncio.QueueFull:
                with suppress(asyncio.QueueEmpty):
                    connection.queue.get_nowait()
                logger.warning(
                    "Cola de salida llena: se descarta el frame mas viejo de un cliente lento"
                )

    async def _writer(self, connection: _Connection) -> None:
        """Unica tarea que escribe en este socket. Nunca lanza hacia arriba.

        Un cliente que expira el timeout, que ya cerro o que rompio el protocolo
        se cierra y se da de baja: dejarlo vivo haria que cada difusion siguiera
        llenandole la cola.
        """
        while True:
            frame = await connection.queue.get()
            try:
                await asyncio.wait_for(connection.websocket.send_text(frame), self._send_timeout_s)
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                logger.warning("Cliente WebSocket lento: se cierra su conexion")
                await self._drop(connection.websocket)
                return
            except Exception:
                # Desconexion durante la difusion: es lo normal cuando alguien
                # cierra la pestaña justo mientras se reparte un frame.
                logger.debug("No se pudo entregar un frame; se descarta la conexion", exc_info=True)
                await self._drop(connection.websocket)
                return

    async def _drop(self, websocket: WebSocket) -> None:
        self.disconnect(websocket)
        with suppress(Exception):
            await asyncio.wait_for(
                websocket.close(code=_SLOW_CLIENT_CLOSE_CODE), self._send_timeout_s
            )
