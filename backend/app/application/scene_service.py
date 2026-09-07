"""Casos de uso de escenas: catalogo y activacion (NEXT_STEPS 6.7).

`SceneService` **compone** sobre `EffectPlayer` y no habla nunca con
`EffectRunner`: la misma relacion que hay entre el reproductor y el bucle. Por
eso aqui no hay ni un fotograma, ni un plazo, ni una cancelacion escrita a mano;
lo unico que este modulo decide es **que** se reproduce y **cuando se rechaza**.

La activacion sigue el orden congelado, y el orden importa:

```text
1. carga la escena y sus objetivos habilitados (UNA consulta, con los efectos)
2. por cada objetivo: resuelve las anulaciones -> EffectPlan
3. valida TODOS los objetivos ANTES de tocar nada          <- ATOMICO
4. cancela el bucle del dispositivo afectado y lo espera   -+ EffectPlayer.start
5. arranca el plan nuevo                                   -+
6. actualiza el estado global (escena activa)
7. publica scene.activated (effect.started ya lo publico el paso 5)
```

**Si el paso 3 falla para cualquier objetivo no se activa nada y se responde
409.** Una escena a medias es peor que una escena rechazada: deja la habitacion
en un estado que el usuario no pidio y que ninguna pantalla sabe describir.

**Durante la reproduccion no se escribe nada en la base.** Ni un fotograma, ni
`device_state`: el estado vivo es el store en memoria y SQLite es cache de
arranque (ARCHITECTURE 4.5).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import UUID, uuid4

from backend.app.application.effect_service import EffectPlayer
from backend.app.application.errors import NothingToActivateError, SceneNotFoundError
from backend.app.application.light_service import require_connected
from backend.app.application.state_store import StateStore
from backend.app.domain.devices.models import DeviceCapabilities
from backend.app.domain.devices.ports import DeviceNotConnectedError
from backend.app.domain.effects.engine import EffectPlan, build_plan
from backend.app.domain.effects.models import ColorSpace
from backend.app.domain.events import SceneActivated
from backend.app.domain.scenes.models import Scene, SceneActivation
from backend.app.domain.scenes.repositories import SceneRepository
from backend.app.domain.state import SceneStatus


class SceneService:
    """Catalogo de escenas y activacion.

    De **vida corta**, uno por peticion, como `EffectService`: usa el repositorio
    de esa `Session` de SQLModel. Lo de larga vida (el reproductor y el store) se
    le inyecta ya construido.

    El repositorio se tipa contra el **Protocol de dominio**, nunca contra la
    implementacion SQLModel: asi el servicio se prueba con un doble en memoria.
    """

    def __init__(
        self,
        *,
        repository: SceneRepository,
        player: EffectPlayer,
        store: StateStore,
        capabilities: DeviceCapabilities,
        max_fps: int,
        color_space: ColorSpace = ColorSpace.HSV,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository = repository
        self._player = player
        self._store = store
        self._capabilities = capabilities
        self._max_fps = max_fps
        self._color_space = color_space
        self._new_id = new_id

    def list_scenes(self) -> Sequence[Scene]:
        """Metodo sincrono: solo lee el repositorio."""
        return self._repository.list_all()

    def get_scene(self, scene_id: UUID) -> Scene:
        scene = self._repository.get(scene_id)
        if scene is None:
            raise SceneNotFoundError(f"No hay ninguna escena guardada con id {scene_id}.")
        return scene

    def save(self, scene: Scene) -> Scene:
        """Crea o reemplaza.

        **No se validan capacidades al guardar**, igual que con los efectos
        (NEXT_STEPS 6.8): una escena puede almacenarse aunque hoy el dispositivo
        conectado no sepa reproducirla. Lo que si se valida es la escena, y eso
        ya lo hace `Scene` al construirse.
        """
        return self._repository.upsert(scene)

    def duplicate(self, scene_id: UUID, *, name: str | None = None) -> Scene:
        """Copia una escena con identidad nueva.

        Como es la regla del modelo la que decide que cambia en una copia (el
        `id`, el nombre y `is_builtin`), aqui solo se encadena leer -> copiar ->
        guardar. El `id` lo genera el SERVIDOR, con una factoria inyectada para
        que los tests sean deterministas.
        """
        original = self.get_scene(scene_id)
        return self._repository.upsert(original.duplicated(self._new_id(), name=name))

    def delete(self, scene_id: UUID) -> None:
        if not self._repository.delete(scene_id):
            raise SceneNotFoundError(f"No hay ninguna escena guardada con id {scene_id}.")

    async def activate(self, scene_id: UUID) -> SceneStatus:
        """Reproduce la escena entera o no reproduce nada.

        La lectura del repositorio corre en el bucle de eventos, igual que las de
        `DeviceService.connect` y `EffectService.start` y por el mismo motivo:
        sacarla exigiria que esta capa importara Starlette e invertiria la
        direccion de las dependencias. Se acepta porque es una lectura acotada y
        no un `commit()`.
        """
        activation = self._repository.get_activation(scene_id)
        if activation is None:
            raise SceneNotFoundError(f"No hay ninguna escena guardada con id {scene_id}.")

        # Paso 3: si algo falla, sale por excepcion aqui, ANTES de que ningun
        # bucle se cancele y sin que el adaptador reciba una sola escritura.
        plans = await self._resolve(activation)

        for plan in plans:
            # Pasos 4 y 5: `start` cancela el bucle anterior, lo espera, marca el
            # estado global y publica `effect.started`. Nada de eso se
            # reimplementa aqui.
            #
            # `keep_scene` porque este arranque ES el de una escena: por defecto
            # `start` suelta la ranura, que es lo correcto cuando quien toma el
            # control es un efecto suelto, pero aqui vaciaria la escena anterior
            # para volver a llenarla dos lineas mas abajo, difundiendo por el
            # camino un estado sin escena que nunca llego a ser cierto.
            await self._player.start(plan, keep_scene=True)

        status = SceneStatus(id=activation.scene.id)
        async with self._store.mutate() as draft:
            draft.set_scene(status)
            draft.event = SceneActivated(scene_id=activation.scene.id)

        return status

    async def _resolve(self, activation: SceneActivation) -> tuple[EffectPlan, ...]:
        """Construye y valida los planes de TODOS los objetivos. **No escribe nada.**

        Es el paso atomico. Devuelve una **tupla ya materializada** y no un
        generador a proposito: con un generador, `build_plan` se ejecutaria
        dentro del bucle de arranque y el primer objetivo ya estaria sonando
        cuando el segundo resultara incompatible, que es exactamente la escena a
        medias que este diseño prohibe.

        Se valida en dos pasadas y en este orden:

        1. **Capacidades y forma del efecto** (`build_plan`): 409 si al
           dispositivo le falta un requisito duro del algoritmo, 422 si el efecto
           no tiene los pasos que su algoritmo necesita.
        2. **Alcance**: el proceso mantiene UN enlace, asi que un objetivo que
           apunta a otro dispositivo no se puede reproducir. Se rechaza en vez de
           saltarselo, por la misma razon de siempre.
        """
        if not activation.targets:
            raise NothingToActivateError(
                f"La escena {activation.scene.name!r} no tiene ningun objetivo habilitado: "
                "añade al menos un dispositivo con su efecto antes de activarla."
            )

        plans = tuple(
            build_plan(
                item.effect,
                capabilities=self._capabilities,
                max_fps=self._max_fps,
                # Un objetivo de escena se traduce en estos DOS parametros y en
                # nada mas; la precedencia frente a los valores del efecto ya
                # esta resuelta dentro de `build_plan`.
                speed=item.target.speed,
                brightness=item.target.brightness,
                color_space=self._color_space,
            )
            for item in activation.targets
        )

        await self._check_reachable(activation)
        return plans

    async def _check_reachable(self, activation: SceneActivation) -> None:
        """Todos los objetivos tienen que caer sobre el enlace abierto.

        `require_connected` aporta la mitad de la regla ("hay algo conectado") y
        se reutiliza en vez de reescribirla: es una regla de negocio y solo puede
        tener una definicion. La otra mitad -- "y es justo este dispositivo" --
        solo tiene sentido aqui, porque solo una escena nombra dispositivos.

        Mientras el proceso mantenga un unico adaptador, una escena con objetivos
        para dos tiras no es activable. Se responde 409 y no se activa la mitad
        que si se puede: media escena es un estado que el usuario no pidio. La
        limitacion desaparece cuando exista un adaptador (y un bucle) por
        dispositivo, sin tocar ni el modelo ni la API.
        """
        await require_connected(self._store)

        status = (await self._store.snapshot()).device
        connected = None if status is None else status.device_id

        for item in activation.targets:
            if item.target.device_id != connected:
                raise DeviceNotConnectedError(
                    f"La escena {activation.scene.name!r} tiene un objetivo para el "
                    f"dispositivo {item.target.device_id}, y el enlace lo ocupa "
                    f"{connected}: conecta ese dispositivo o deshabilita el objetivo."
                )
