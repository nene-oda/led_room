"""Casos de uso de efectos: catalogo, reproduccion y estado global.

Dos clases, con dos motivos de cambio distintos y dos vidas distintas:

* **`EffectPlayer`** — de **larga vida**. Envuelve al `EffectRunner` con lo que
  el runner deliberadamente no conoce: el estado global y los eventos. Es
  tambien la funcion de preempcion que recibe `LightService`, y por eso tiene
  que sobrevivir a la peticion.
* **`EffectService`** — de **vida corta**, uno por peticion, como
  `DeviceService`: usa el repositorio de esa `Session` de SQLModel para el CRUD
  y delega la reproduccion en el reproductor.

`effect.started` y `effect.stopped` se publican **aqui**, nunca desde el dominio
ni desde el runner: el motor no conoce el WebSocket (NEXT_STEPS 6.7). Y durante
la reproduccion no se escribe **nada** en la base: cero `save_state`, cero
fotogramas persistidos (ARCHITECTURE 4.5).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

from backend.app.application.effect_runner import EffectRunner, StopReason
from backend.app.application.errors import EffectNotFoundError
from backend.app.application.light_service import require_connected
from backend.app.application.state_store import StateStore
from backend.app.domain.devices.models import DeviceCapabilities
from backend.app.domain.effects.engine import EffectPlan, build_plan
from backend.app.domain.effects.models import ColorSpace, EffectDefinition
from backend.app.domain.effects.repositories import EffectRepository
from backend.app.domain.events import EffectStarted, EffectStopped
from backend.app.domain.state import EffectStatus

logger = logging.getLogger(__name__)


class EffectPlayer:
    """Estado global y eventos alrededor del unico bucle de reproduccion.

    Existe separado del runner porque las dos piezas cambian por motivos
    distintos: el runner cambia si cambia la politica de cadencia o de descarte;
    este cambia si cambia el contrato de eventos o la forma del estado global.
    Fundirlos daria una clase que sabe de plazos, de fotogramas, del store y del
    catalogo de eventos a la vez.
    """

    def __init__(self, runner: EffectRunner, store: StateStore) -> None:
        self._runner = runner
        self._store = store

    async def start(self, plan: EffectPlan, *, keep_scene: bool = False) -> EffectStatus:
        """Sustituye lo que estuviera sonando por este plan.

        El estado se marca **antes** de arrancar la tarea, no despues: un
        `STATIC` de un solo fotograma puede terminar durante el propio `play()`,
        y con el orden inverso su `effect.stopped` llegaria antes que el
        `effect.started` y el estado global se quedaria describiendo un efecto ya
        terminado.

        No se publica `effect.stopped` del efecto al que se sustituye: el
        `effect.started` del nuevo ya dice que el anterior dejo de sonar, y dos
        eventos para una sola transicion obligarian al cliente a ordenarlos.

        `keep_scene` lo pone **solo** `SceneService.activate`, que es quien esta
        arrancando el efecto *de* una escena y pondra su ranura justo despues.
        Sin el, arrancar un efecto suelto encima de una escena dejaria `scene`
        describiendo algo que ya no suena; con el a `False` por defecto, esa
        limpieza ocurre sin que ningun llamante tenga que acordarse.
        """
        await require_connected(self._store)

        status = EffectStatus(running=True, id=plan.effect_id)
        async with self._store.mutate() as draft:
            released = not keep_scene and draft.state.scene is not None
            if released:
                draft.set_scene(None)

            draft.set_effect(status)
            draft.event = EffectStarted(effect_id=plan.effect_id)

        if released:
            await self._announce_release()

        await self._runner.play(plan, on_finished=self._finished)
        return status

    async def stop(self, effect_id: UUID | None = None) -> None:
        """Para el efecto activo. **Idempotente** y barata cuando no hay ninguno.

        Sin `effect_id` para lo que sea que suene: asi la usa `LightService` como
        preempcion, en cada comando manual, incluidos los ~20 por segundo de un
        arrastre. Por eso la salida rapida no es un lujo: es lo que impide tomar
        el cerrojo del store dos veces por cada valor del arrastre.

        Con `effect_id`, solo si es ese el que esta sonando. Parar por id un
        efecto que ya sustituyo otro apagaria el que el usuario acaba de
        arrancar.

        La salida rapida mira **tambien** la escena: una escena cuyo efecto ya
        termino solo (un `STATIC` dura un fotograma) deja `effect` a `None` y
        `scene` puesta, y sin esa tercera condicion el primer comando manual
        salia por aqui y la escena se quedaba en el estado global para siempre.
        Cuesta una lectura sin cerrojo y solo la primera vez: en cuanto la
        escena se suelta, el arrastre vuelve a la ruta barata.
        """
        state = await self._store.snapshot()
        current = state.effect
        if not self._runner.is_running and current is None and state.scene is None:
            return
        if effect_id is not None and (current is None or current.id != effect_id):
            return

        await self._runner.stop()
        await self._clear(release_scene=True)

    async def _finished(self, effect_id: UUID, reason: StopReason) -> None:
        """El efecto acabo solo: se agoto, fallo la escritura o se cayo el enlace.

        Nunca se llama tras una cancelacion; ahi manda quien cancelo.

        **No suelta la escena** (`release_scene` se queda a `False`): que el
        efecto de una escena llegue a su ultimo fotograma no la termina. La tira
        sigue mostrando exactamente lo que la escena pidio -- el `finally` del
        runner no apaga la luz a proposito -- y borrarla aqui haria que activar
        una escena de un solo `STATIC` la vaciara del estado global una fraccion
        de segundo despues de ponerla.
        """
        if reason is not StopReason.COMPLETED:
            logger.info("Efecto %s terminado (%s)", effect_id, reason.value)
        await self._clear(effect_id)

    async def _clear(self, effect_id: UUID | None = None, *, release_scene: bool = False) -> None:
        """Vacia la ranura de efecto y publica `effect.stopped`.

        Con `effect_id`, solo si es ese el que consta: una notificacion tardia
        de un efecto ya sustituido no puede borrar al que suena ahora.

        Con `release_scene`, vacia **ademas** la ranura de escena: quien para el
        efecto que una escena puso le esta quitando el control, y dejar `scene`
        con `effect: null` describe una escena que ya no suena.

        Si no hay nada que borrar, el estado no cambia, y entonces el store no
        incrementa `version` ni publica: parar dos veces no inunda a los
        clientes con paradas que no ocurrieron.
        """
        released = False
        async with self._store.mutate() as draft:
            if release_scene and draft.state.scene is not None:
                draft.set_scene(None)
                released = True

            current = draft.state.effect
            if current is not None and (effect_id is None or current.id == effect_id):
                draft.set_effect(None)
                draft.event = EffectStopped(effect_id=current.id)

        if released:
            await self._announce_release()

    async def _announce_release(self) -> None:
        """Difunde el estado completo tras soltar una escena.

        Hace falta porque ninguno de los nombres congelados de ARCHITECTURE 3.6
        describe "la escena dejo de estar activa": `effect.stopped` solo lleva el
        `effect_id`, asi que un cliente que solo aplicara eventos se quedaria
        mostrando la escena para siempre. Es el mismo recurso, y por el mismo
        motivo, que usa `DeviceService.connect` tras rehidratar la luz.

        Se llama **fuera** de `mutate()`: el estado ya esta confirmado, y el
        cerrojo no es reentrante.
        """
        await self._store.publish_snapshot()


class EffectService:
    """Catalogo de efectos y arranque de la reproduccion.

    El repositorio se tipa contra el **Protocol de dominio**, nunca contra la
    implementacion SQLModel: asi el servicio se prueba con un doble en memoria.
    """

    def __init__(
        self,
        *,
        repository: EffectRepository,
        player: EffectPlayer,
        capabilities: DeviceCapabilities,
        max_fps: int,
        color_space: ColorSpace = ColorSpace.HSV,
    ) -> None:
        self._repository = repository
        self._player = player
        self._capabilities = capabilities
        self._max_fps = max_fps
        self._color_space = color_space

    def list_effects(self) -> Sequence[EffectDefinition]:
        """Metodo sincrono: solo lee el repositorio."""
        return self._repository.list_all()

    def get_effect(self, effect_id: UUID) -> EffectDefinition:
        effect = self._repository.get(effect_id)
        if effect is None:
            raise EffectNotFoundError(f"No hay ningun efecto guardado con id {effect_id}.")
        return effect

    def save(self, effect: EffectDefinition) -> EffectDefinition:
        """Crea o reemplaza.

        **No se validan capacidades al guardar** (NEXT_STEPS 6.8): un efecto
        puede almacenarse aunque hoy ningun dispositivo conectado sepa
        reproducirlo. Lo que si se valida es el propio efecto, y eso ya lo hace
        `EffectDefinition` al construirse.
        """
        return self._repository.upsert(effect)

    def delete(self, effect_id: UUID) -> None:
        if not self._repository.delete(effect_id):
            raise EffectNotFoundError(f"No hay ningun efecto guardado con id {effect_id}.")

    async def start(self, effect_id: UUID, *, speed: int | None = None) -> EffectStatus:
        """Carga, resuelve y reproduce.

        La lectura del repositorio corre en el bucle de eventos, igual que las de
        `DeviceService.connect` y por el mismo motivo: sacarla exigiria que esta
        capa importara Starlette, e invertiria la direccion de las dependencias.
        Se acepta porque es una lectura por clave primaria y no un `commit()`.

        El plan se construye **antes** de tocar nada: si al dispositivo le falta
        una capacidad dura (409) o el efecto no tiene los pasos que su algoritmo
        necesita (422), el adaptador no recibe ni una sola escritura.
        """
        definition = self.get_effect(effect_id)
        plan = build_plan(
            definition,
            capabilities=self._capabilities,
            max_fps=self._max_fps,
            speed=speed,
            color_space=self._color_space,
        )
        return await self._player.start(plan)

    async def stop(self, effect_id: UUID) -> None:
        """Para el efecto indicado. 404 si no existe; no-op si no era el que sonaba."""
        self.get_effect(effect_id)
        await self._player.stop(effect_id)
