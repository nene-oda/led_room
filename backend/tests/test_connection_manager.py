"""El gestor de conexiones: la pieza que decide si un cliente degrada a todos.

No tenia ni un test propio, y es la que responde a las preguntas caras: que pasa
con un cliente que no drena, con uno que ya cerro, y si una difusion puede
retrasar los comandos de los demas.

Los dobles de aqui son `WebSocket` de mentira a proposito: `TestClient` no
permite fabricar un cliente que tarde 3 s en aceptar un frame, que es justo el
caso que hay que probar.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import pytest
from starlette.websockets import WebSocket

from backend.app.domain.events import DomainEvent, LightPowerChanged, StateSnapshot
from backend.app.domain.state import GlobalState
from backend.app.websocket.manager import ConnectionManager

EVENT = LightPowerChanged(power=True)


class FakeWebSocket:
    """Cliente programable: latencia, fallo y cierre observables."""

    def __init__(self, *, latency_s: float = 0.0) -> None:
        self.latency_s = latency_s
        self.frames: list[dict[str, Any]] = []
        self.failure: Exception | None = None
        self.accepted = False
        self.close_codes: list[int] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        if self.failure is not None:
            raise self.failure
        self.frames.append(json.loads(text))

    async def close(self, code: int = 1000) -> None:
        self.close_codes.append(code)

    @property
    def types(self) -> list[str]:
        return [frame["type"] for frame in self.frames]


def _as_websocket(fake: FakeWebSocket) -> WebSocket:
    """El gestor solo usa `accept`, `send_text` y `close`; el doble los cumple."""
    return cast(WebSocket, fake)


async def _register(manager: ConnectionManager, fake: FakeWebSocket) -> None:
    websocket = _as_websocket(fake)
    await manager.accept(websocket)
    manager.register(websocket)


async def _drain(*fakes: FakeWebSocket, expected: int, timeout_s: float = 2.0) -> None:
    """Espera a que las tareas escritoras entreguen lo encolado."""
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if all(len(fake.frames) >= expected for fake in fakes):
            return
        await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_dar_de_alta_es_idempotente_y_no_duplica_escritoras() -> None:
    manager = ConnectionManager()
    fake = FakeWebSocket()
    websocket = _as_websocket(fake)

    await manager.accept(websocket)
    manager.register(websocket)
    manager.register(websocket)

    assert fake.accepted
    assert manager.count == 1

    await manager.publish(EVENT, 1)
    await _drain(fake, expected=1)

    assert fake.types == ["light.power.changed"], (
        "Dos escritoras habrian entregado el frame dos veces"
    )

    manager.disconnect(websocket)


@pytest.mark.asyncio
async def test_dar_de_baja_dos_veces_no_falla_y_deja_de_recibir() -> None:
    manager = ConnectionManager()
    fake = FakeWebSocket()
    websocket = _as_websocket(fake)
    await _register(manager, fake)

    manager.disconnect(websocket)
    manager.disconnect(websocket)

    assert manager.count == 0

    await manager.publish(EVENT, 1)
    await asyncio.sleep(0.02)

    assert fake.frames == []


@pytest.mark.asyncio
async def test_enviar_a_una_conexion_desconocida_no_falla() -> None:
    """El endpoint puede intentar responder un `error` a un socket que ya se fue."""
    manager = ConnectionManager()
    fake = FakeWebSocket()

    await manager.send(_as_websocket(fake), EVENT, 1)

    assert fake.frames == []


@pytest.mark.asyncio
async def test_un_cliente_que_no_drena_se_cierra_con_1011_y_se_da_de_baja() -> None:
    """La rama de timeout: dejarlo vivo haria que cada difusion le llenase la cola."""
    manager = ConnectionManager(send_timeout_s=0.02)
    lento = FakeWebSocket(latency_s=5.0)
    await _register(manager, lento)

    await manager.publish(EVENT, 1)
    await asyncio.sleep(0.1)

    assert manager.count == 0
    assert lento.close_codes == [1011]
    assert lento.frames == []


@pytest.mark.asyncio
async def test_un_socket_que_ya_cerro_se_descarta_sin_romper_la_difusion() -> None:
    """Desconexion DURANTE el reparto: es lo normal al cerrar la pestaña."""
    manager = ConnectionManager(send_timeout_s=0.5)
    superviviente = FakeWebSocket()
    caido = FakeWebSocket()
    caido.failure = RuntimeError("websocket ya cerrado")
    await _register(manager, superviviente)
    await _register(manager, caido)

    await manager.publish(EVENT, 1)
    await _drain(superviviente, expected=1)
    await asyncio.sleep(0.02)

    assert superviviente.types == ["light.power.changed"]
    assert manager.count == 1, "El caido debe quedar fuera; el superviviente, dentro"
    assert caido.close_codes == [1011]


@pytest.mark.asyncio
async def test_un_cliente_lento_no_retrasa_la_difusion_de_los_demas() -> None:
    """I2: `publish` no espera a la red, asi que no retiene el cerrojo del estado.

    Antes, `publish` hacia `gather` con un `wait_for` por cliente y se llamaba
    DENTRO del cerrojo global: un socket que no drenaba costaba 1,01 s por
    comando y uno de 100 ms bajaba la cadencia de 20 act./s a ~9.
    """
    manager = ConnectionManager(send_timeout_s=1.0)
    rapido = FakeWebSocket()
    lento = FakeWebSocket(latency_s=0.2)
    await _register(manager, rapido)
    await _register(manager, lento)

    inicio = asyncio.get_running_loop().time()
    for version in range(1, 11):
        await manager.publish(EVENT, version)
    publicar = asyncio.get_running_loop().time() - inicio

    await _drain(rapido, expected=10)

    assert publicar < 0.05, f"Publicar diez veces tardo {publicar:.3f} s: alguien espero a la red"
    assert len(rapido.frames) == 10
    assert len(lento.frames) < 10, "El lento va por detras; los demas no le esperan"

    manager.disconnect(_as_websocket(rapido))
    manager.disconnect(_as_websocket(lento))


@pytest.mark.asyncio
async def test_la_cola_llena_descarta_el_frame_mas_viejo() -> None:
    """Un hueco es preferible a una cola de valores obsoletos; la `version` lo delata."""
    manager = ConnectionManager(send_timeout_s=1.0, queue_size=2)
    lento = FakeWebSocket(latency_s=0.05)
    await _register(manager, lento)

    for version in range(1, 21):
        await manager.publish(EVENT, version)

    await asyncio.sleep(0.5)

    versiones = [frame["version"] for frame in lento.frames]
    assert versiones, "Algo tuvo que entregarse"
    assert len(versiones) < 20, "Sin descarte, el cliente lento acumularia los 20 frames"
    assert versiones == sorted(versiones), "Nunca se entrega un frame mas viejo tras uno nuevo"
    assert versiones[-1] == 20, "El ultimo estado SIEMPRE llega: es lo que deja la UI coherente"

    manager.disconnect(_as_websocket(lento))


@pytest.mark.asyncio
async def test_el_snapshot_solo_va_a_su_destinatario() -> None:
    manager = ConnectionManager()
    nuevo = FakeWebSocket()
    otro = FakeWebSocket()
    await _register(manager, nuevo)
    await _register(manager, otro)

    await manager.send(_as_websocket(nuevo), StateSnapshot(state=GlobalState()), 0)
    await _drain(nuevo, expected=1)
    await asyncio.sleep(0.02)

    assert nuevo.types == ["state.snapshot"]
    assert otro.frames == []

    await manager.close_all()


@pytest.mark.asyncio
async def test_publicar_sin_clientes_no_falla() -> None:
    await ConnectionManager().publish(EVENT, 1)


@pytest.mark.asyncio
async def test_el_cierre_ordenado_no_deja_tareas_vivas() -> None:
    """El `lifespan` lo llama: una escritora huerfana sobreviviria al proceso."""
    base = len(asyncio.all_tasks())
    manager = ConnectionManager()
    for _ in range(3):
        await _register(manager, FakeWebSocket())

    assert len(asyncio.all_tasks()) > base

    await manager.close_all()
    await asyncio.sleep(0.02)

    assert manager.count == 0
    assert len(asyncio.all_tasks()) == base


@pytest.mark.asyncio
async def test_un_fallo_de_difusion_nunca_sube_al_llamante() -> None:
    """`EventPublisher` promete no lanzar: el store confia en ello para no deshacer."""
    manager = ConnectionManager(send_timeout_s=0.05)
    roto = FakeWebSocket()
    roto.failure = RuntimeError("transporte roto")
    await _register(manager, roto)

    event: DomainEvent = EVENT
    await manager.publish(event, 1)
    await manager.send(_as_websocket(roto), event, 1)
    await asyncio.sleep(0.05)

    assert manager.count == 0


@pytest.mark.parametrize(("send_timeout_s", "queue_size"), [(0.0, 8), (-1.0, 8), (1.0, 0)])
def test_los_ajustes_invalidos_se_rechazan(send_timeout_s: float, queue_size: int) -> None:
    with pytest.raises(ValueError):
        ConnectionManager(send_timeout_s=send_timeout_s, queue_size=queue_size)
