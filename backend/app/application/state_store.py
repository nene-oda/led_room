"""Titular unico del estado global autoritativo (NEXT_STEPS A4, ARCHITECTURE 4).

```text
Fuente de verdad   = este store, en memoria del proceso backend
SQLite             = cache de arranque (ultimo estado deseado; no se lee en caliente)
Adaptador/hardware = sumidero (no se le consulta el estado)
Clientes (React)   = replicas; el servidor gana siempre
```

**Toda** mutacion del estado pasa por aqui: ninguna ruta HTTP ni el endpoint
WebSocket tocan `GlobalState` directamente. Y el store publica el evento
resultante a traves de `EventPublisher`, nunca importando `websocket/`: es esa
direccion de dependencia la que impide que la capa de aplicacion acabe
conociendo el transporte.

**Orden de operaciones, unico para REST y WS** (NEXT_STEPS A4):

```text
comando -> validar (rango + capacidades) -> escribir en el dispositivo
        -> actualizar el store (version+1) -> publicar evento
```

La escritura en el dispositivo va DENTRO del `async with store.mutate()`, y esa
es la pieza que hace cumplir la regla: si la escritura lanza, el bloque sale por
excepcion, no se confirma nada y no se publica nada. Publicar antes de escribir
desincronizaria a los clientes justo cuando el enlace BLE se cae, que es cuando
la sincronia importa.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backend.app.application.ports import EventPublisher
from backend.app.domain.devices.models import DeviceStatus
from backend.app.domain.events import DomainEvent, StateSnapshot
from backend.app.domain.lighting import LightState
from backend.app.domain.state import EffectStatus, GlobalState, SceneStatus

logger = logging.getLogger(__name__)


class StateDraft:
    """El estado siguiente mientras se construye, dentro del cerrojo del store.

    No expone `state` como atributo asignable: los cambios se hacen con los
    metodos `set_*`, que son los unicos campos de `GlobalState` con un caso de
    uso propietario hoy. Asi es imposible confirmar un estado a medio
    construir o saltarse el incremento de `version`.
    """

    def __init__(self, state: GlobalState) -> None:
        self._state = state
        #: Que se publicara si la mutacion se confirma. `None` = cambio de
        #: estado sin evento congelado que lo describa (p. ej. anotar el
        #: `last_error` de un `connect()` fallido durante el arranque).
        self.event: DomainEvent | None = None

    @property
    def state(self) -> GlobalState:
        """Estado en construccion; tras salir del bloque, el ya confirmado."""
        return self._state

    def set_light(self, light: LightState) -> None:
        self._state = self._state.model_copy(update={"light": light})

    def set_device(self, device: DeviceStatus | None) -> None:
        self._state = self._state.model_copy(update={"device": device})

    def set_effect(self, effect: EffectStatus | None) -> None:
        """Efecto en curso; `None` cuando no suena ninguno.

        Lo escribe SOLO `application/effect_service.py`, que es el titular del
        caso de uso. El bucle de reproduccion no toca el estado global: no debe
        conocer ni el store ni el WebSocket.
        """
        self._state = self._state.model_copy(update={"effect": effect})

    def set_scene(self, scene: SceneStatus | None) -> None:
        """Escena activa; `None` cuando no hay ninguna.

        La **pone** solo `application/scene_service.py`, que es el titular del
        caso de uso, igual que `set_effect` lo escribe solo el reproductor de
        efectos. Una escena y el efecto que esta sonando son dos hechos
        distintos y se guardan por separado a proposito: el usuario puede
        arrancar un efecto suelto sin que haya ninguna escena de por medio.

        La **suelta** ademas `EffectPlayer`, y solo a `None`: quien preempta el
        efecto que una escena puso (un comando manual o un efecto suelto) es el
        unico que sabe que la escena dejo de tener el control, y hacerlo alli
        evita que cada llamante tenga que acordarse de limpiarla.
        """
        self._state = self._state.model_copy(update={"scene": scene})

    def _commit(self, committed: GlobalState) -> None:
        """Fija el estado ya confirmado (con su `version`) para que el llamante
        lo lea tras el bloque sin volver a pedir un snapshot.

        Lo llama SOLO `StateStore.mutate`, y es un metodo en vez de una
        escritura directa sobre `draft._state` desde el store: asi la intencion
        ("esto ya esta confirmado") queda en el tipo que la representa.
        """
        self._state = committed


class StateStore:
    """Unico objeto mutable del estado global. Protegido con un `asyncio.Lock`.

    Todos sus metodos son `async` a proposito: una dependencia sincrona de
    FastAPI corre en el threadpool, y desde alli no se puede llamar a nada de
    aqui. El estado global es afin al bucle de eventos y esa firma lo hace
    cumplir sin necesidad de disciplina.
    """

    def __init__(self, publisher: EventPublisher, *, initial: GlobalState | None = None) -> None:
        self._publisher = publisher
        self._state = initial if initial is not None else GlobalState()
        self._lock = asyncio.Lock()

    async def snapshot(self) -> GlobalState:
        """Estado actual completo. Cuerpo de `GET /api/v1/state` y de `state.snapshot`.

        NO toma el cerrojo: `GlobalState` es inmutable y confirmar una mutacion
        es una unica asignacion de atributo, asi que un lector siempre ve una
        version coherente. Tomarlo haria que una escritura BLE colgada (hasta
        `LED_ROOM_BLE_WRITE_TIMEOUT`) bloqueara tambien las lecturas de estado.
        """
        return self._state

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[GlobalState]:
        """Cede el estado con el cerrojo de las difusiones TOMADO.

        Existe para dar de alta un cliente WebSocket y mandarle su
        `state.snapshot` de forma atomica respecto a las difusiones. Sin esto,
        el endpoint daba de alta el socket y capturaba el snapshot despues, y un
        evento publicado en esa ventana podia entregarse ANTES del snapshot: el
        cliente aplicaba el cambio y a continuacion el estado viejo que lo
        contradecia, quedandose desincronizado de forma permanente.

        Invertir el orden (mandar el snapshot y dar de alta despues) no sirve:
        perderia los eventos de esa misma ventana.

        **Dentro de este bloque no debe haber ninguna espera de red.** El
        cerrojo que se toma aqui es el que serializa todos los comandos de luz:
        un `accept()` o un `send()` que bloqueen dentro dejarian sin servicio al
        resto de clientes. Dar de alta la conexion y encolarle un frame no ceden
        el control, y ese es justamente el contrato que lo hace seguro.
        """
        async with self._lock:
            yield self._state

    @asynccontextmanager
    async def mutate(self) -> AsyncIterator[StateDraft]:
        """Mutacion transaccional del estado global.

        Uso, con la escritura al dispositivo dentro del bloque:

        ```python
        async with store.mutate() as draft:
            await device.set_power(True)              # si lanza, no hay cambio
            draft.set_light(light)
            draft.event = LightPowerChanged(power=True)
        return draft.state.light                      # ya con la version nueva
        ```

        * Si el cuerpo lanza, no se confirma ni se publica nada.
        * Si el cuerpo no cambia el estado, tampoco: es lo que hace idempotente
          un `disconnect` sobre algo ya desconectado (ni `version`, ni evento).
        * Si lo cambia, se incrementa `version` y se publica `draft.event`.

        El cerrojo NO es reentrante: nadie debe anidar dos `mutate()`.
        """
        async with self._lock:
            previous = self._state
            draft = StateDraft(previous)

            yield draft

            if draft.state is previous:
                return

            committed = draft.state.model_copy(update={"version": previous.version + 1})
            self._state = committed
            draft._commit(committed)

            if draft.event is not None:
                # Dentro del cerrojo: el orden de publicacion debe coincidir con
                # el orden de `version`, o un cliente aplicaria un cambio viejo
                # despues de uno nuevo.
                await self._publish(draft.event)

    async def publish_snapshot(self) -> None:
        """Difunde el estado completo a todos los clientes.

        Lo usa `DeviceService.connect`: los eventos congelados de ARCHITECTURE
        3.6 solo llevan el campo que cambio, asi que tras una conexion (que
        rehidrata la luz con el estado deseado persistido) el resto de clientes
        se quedarian mostrando un color que ya no es el vigente.
        """
        await self._publish(StateSnapshot(state=self._state))

    async def _publish(self, event: DomainEvent) -> None:
        """Publica sin poder deshacer lo ya aplicado, sellado con la `version`.

        Se llama SIEMPRE dentro del cerrojo y justo despues de confirmar, asi
        que `self._state.version` es exactamente la version que describe el
        evento. Es lo que permite al cliente detectar un hueco: dos huecos
        existen por diseño y ninguno era detectable sin este numero.

        1. `DeviceService._record_failure` gasta una version sin publicar nada.
        2. Un cliente lento pierde frames descartados por su cola de salida.

        En ambos casos el cliente ve un salto de `version` y rehidrata con
        `GET /api/v1/state` en vez de quedarse mostrando un estado viejo.

        `EventPublisher.publish` promete no lanzar por culpa de un cliente lento
        o caido. Se comprueba aqui en vez de confiar: un fallo de difusion no
        puede convertir en error una operacion que el hardware ya acepto y que
        el store ya confirmo.
        """
        try:
            await self._publisher.publish(event, self._state.version)
        except Exception:
            logger.exception("No se pudo difundir el evento %s", event.type)
