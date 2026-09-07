"""Dobles de test compartidos.

`NullLightDeviceAdapter` **no** vale para esto y no debe convertirse en un mock:
es codigo de produccion cuyo unico motivo de cambio es "arrancar sin radio".
Darle historial de escrituras, latencia y fallos programables le daria un
segundo motivo de cambio y ataria el comportamiento del servicio a las
necesidades de la suite.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from uuid import UUID

from backend.app.config import Settings
from backend.app.domain.devices.models import (
    SINGLE_COLOR_STRIP,
    Device,
    DeviceCapabilities,
    DeviceTarget,
    DiscoveredDevice,
)
from backend.app.domain.effects.models import EffectDefinition
from backend.app.domain.events import DomainEvent
from backend.app.domain.lighting import LightFrame, LightState
from backend.app.domain.profiles.models import Profile
from backend.app.domain.scenes.models import Scene, SceneActivation, SceneTargetEffect
from backend.app.domain.state import SceneStatus
from backend.app.infrastructure.persistence.database import create_all, create_database_engine


@dataclass(frozen=True, slots=True)
class WriteRecord:
    """Una escritura observada, con el intervalo que ocupo."""

    operation: str
    started_at: float
    finished_at: float


class RecordingLightDevice:
    """Doble de `LightDevicePort` que registra cuando empieza y acaba cada escritura.

    Programable con tres palancas independientes:

    * `latency_s` — cuanto tarda cada escritura.
    * `hangs` — la escritura no retorna nunca (write colgado).
    * `failure` — la escritura lanza esa excepcion.
    """

    def __init__(
        self,
        *,
        latency_s: float = 0.0,
        capabilities: DeviceCapabilities = SINGLE_COLOR_STRIP,
    ) -> None:
        self.writes: list[WriteRecord] = []
        self.latency_s = latency_s
        self.hangs = False
        self.failure: Exception | None = None
        self.connect_calls = 0
        self.disconnect_calls = 0
        #: Destinos con los que se pidio abrir el enlace, en orden. Es lo que
        #: permite comprobar que `Device.address` llega de verdad al adaptador.
        self.targets: list[DeviceTarget] = []
        self._capabilities = capabilities
        self._connected = False

    @property
    def capabilities(self) -> DeviceCapabilities:
        return self._capabilities

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self, target: DeviceTarget) -> None:
        self.connect_calls += 1
        self.targets.append(target)
        self._connected = True

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._connected = False

    async def set_power(self, value: bool) -> None:
        await self._record(f"set_power:{value}")

    async def set_color(self, red: int, green: int, blue: int) -> None:
        await self._record(f"set_color:{red},{green},{blue}")

    async def set_brightness(self, brightness: int) -> None:
        await self._record(f"set_brightness:{brightness}")

    async def apply_frame(self, frame: LightFrame) -> None:
        await self._record(f"apply_frame:{frame.color.to_hex()}@{frame.brightness}")

    async def _record(self, operation: str) -> None:
        started = time.perf_counter()
        try:
            # Dos cesiones al bucle: una corrutina sin ningun punto de
            # suspension no le da a otra la oportunidad de intercalarse, y el
            # test de serializacion pasaria sin haber probado nada.
            await asyncio.sleep(self.latency_s)
            await asyncio.sleep(0)
            if self.hangs:
                await asyncio.Event().wait()  # nunca se despierta
            if self.failure is not None:
                raise self.failure
        finally:
            self.writes.append(WriteRecord(operation, started, time.perf_counter()))

    @property
    def operations(self) -> list[str]:
        return [write.operation for write in self.writes]


def overlapping(writes: Sequence[WriteRecord]) -> list[tuple[WriteRecord, WriteRecord]]:
    """Pares de escrituras cuyos intervalos se solapan. Vacio = serializadas."""
    ordered = sorted(writes, key=lambda write: write.started_at)
    return [
        (first, second)
        for first, second in pairwise(ordered)
        if second.started_at < first.finished_at
    ]


class RecordingEventPublisher:
    """Doble de `EventPublisher` que conserva lo publicado, en orden.

    `failure` permite comprobar la promesa del puerto: un cliente lento o caido
    no puede deshacer un cambio que el hardware ya acepto.
    """

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []
        self.versions: list[int] = []
        self.failure: Exception | None = None

    async def publish(self, event: DomainEvent, version: int) -> None:
        self.events.append(event)
        self.versions.append(version)
        if self.failure is not None:
            raise self.failure

    @property
    def types(self) -> list[str]:
        return [event.type.value for event in self.events]


class SkewedEventPublisher(RecordingEventPublisher):
    """Publicador cuyo primer frame tarda MAS que los siguientes.

    Modela lo unico que puede desordenar una difusion: que entregar un frame
    lleve un tiempo distinto en cada llamada (tamaño del frame, cliente lento,
    reparto a N sockets). Un publicador de latencia cero -- o incluso uno con un
    `sleep(0)` fijo -- no puede reordenar nada, asi que un test de orden que lo
    use pasa igual con cerrojo y sin el.

    Con la publicacion DENTRO del cerrojo el desorden es imposible; sacandola
    fuera, este doble lo destapa de forma determinista.
    """

    def __init__(self, *, slowest_s: float = 0.02, count: int = 20) -> None:
        super().__init__()
        self._slowest_s = slowest_s
        self._count = count

    async def publish(self, event: DomainEvent, version: int) -> None:
        remaining = max(self._count - version, 0)
        await asyncio.sleep(self._slowest_s * remaining / max(self._count, 1))
        await super().publish(event, version)


class InMemoryDeviceRepository:
    """Doble de `DeviceRepository` con la MISMA semantica de identidad que SQLite.

    Reproduce a proposito las dos reglas del repositorio real: `upsert` resuelve
    primero por `id` y despues por `(adapter_type, address)`, y cuando gana la
    segunda **el id persistido manda sobre el recibido**. Un doble que no
    respetara eso dejaria pasar un servicio que reescribe claves primarias.
    """

    def __init__(self, devices: Sequence[Device] = ()) -> None:
        self.devices: dict[UUID, Device] = {device.id: device for device in devices}
        self.states: dict[UUID, LightState] = {}
        self.saved_states: list[tuple[UUID, LightState]] = []

    def get(self, device_id: UUID) -> Device | None:
        return self.devices.get(device_id)

    def get_by_address(self, address: str) -> Device | None:
        return next(
            (device for device in self.devices.values() if device.address == address),
            None,
        )

    def list_enabled(self) -> Sequence[Device]:
        return sorted(
            (device for device in self.devices.values() if device.enabled),
            key=lambda device: device.name,
        )

    def upsert(self, device: Device) -> Device:
        existing = self.devices.get(device.id)
        if existing is None and device.address is not None:
            existing = next(
                (
                    candidate
                    for candidate in self.devices.values()
                    if candidate.adapter_type == device.adapter_type
                    and candidate.address == device.address
                ),
                None,
            )

        stored = device if existing is None else device.model_copy(update={"id": existing.id})
        self.devices[stored.id] = stored
        return stored

    def load_state(self, device_id: UUID) -> LightState | None:
        return self.states.get(device_id)

    def save_state(self, device_id: UUID, state: LightState) -> None:
        self.states[device_id] = state
        self.saved_states.append((device_id, state))


def api_settings(tmp_path: Path) -> Settings:
    """Ajustes para los tests de la API: base temporal con el esquema ya creado.

    El `lifespan` abre la base pero NO crea el esquema (eso lo hace Alembic desde
    el entrypoint del contenedor), asi que aqui se crea antes de arrancar la
    aplicacion. `create_all` es legitimo en tests y solo en tests.

    El frontend apunta a un directorio inexistente a proposito: estos tests
    prueban la API, y con el SPA montado el catch-all podria enmascarar un 404.
    """
    settings = Settings(database=tmp_path / "led-room.db", frontend=tmp_path / "sin-frontend")

    engine = create_database_engine(settings.database)
    try:
        create_all(engine)
    finally:
        engine.dispose()

    return settings


class ConnectedLightDevice(RecordingLightDevice):
    """Como `RecordingLightDevice`, pero ya enlazado.

    Sirve para inyectar un `LightService` sobre un dispositivo con capacidades o
    fallos concretos sin tener que abrir el enlace desde un test sincrono.
    """

    @property
    def is_connected(self) -> bool:
        return True


class SlowDiscovery:
    """Doble de `DeviceDiscoveryPort` que tarda lo que se le diga.

    Necesario para observar dos escaneos solapados: el descubridor nulo responde
    de inmediato y nunca coincidirian.
    """

    def __init__(self, *, delay_s: float = 0.05, devices: Sequence[DiscoveredDevice] = ()) -> None:
        self.delay_s = delay_s
        self.timeouts: list[float] = []
        self._devices: tuple[DiscoveredDevice, ...] = tuple(devices)

    async def scan(self, timeout_s: float) -> Sequence[DiscoveredDevice]:
        self.timeouts.append(timeout_s)
        await asyncio.sleep(self.delay_s)
        return self._devices


class ManualClock:
    """Reloj de tiempo VIRTUAL. Cumple `backend.app.application.clock.Clock`.

    Un test que tarda 4 s en verificar una transicion de 4 s es un test que nadie
    ejecuta (NEXT_STEPS 6.9). Aqui `sleep` no espera: adelanta el contador y cede
    el control una vez, que es lo que permite que la tarea del efecto y el test
    se intercalen de forma determinista.

    `advance` existe aparte para que un doble de dispositivo pueda "gastar"
    tiempo simulando su latencia sin que eso cuente como una espera del motor.
    """

    def __init__(self, *, start: float = 0.0) -> None:
        self.now = start
        #: Cada espera pedida por el motor, en segundos y en orden.
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


class ClockedLightDevice:
    """Doble de `LightDevicePort` cuya latencia consume tiempo VIRTUAL.

    `RecordingLightDevice` mide con `time.perf_counter` y duerme de verdad: sirve
    para comprobar solapamientos, no para probar el motor de efectos, que no debe
    esperar ni un milisegundo real. Este registra los fotogramas aplicados y
    avanza el `ManualClock`, de modo que "el adaptador tarda 3x el periodo" es
    exactamente reproducible.

    Tres palancas independientes:

    * `latency_s` — cuanto tarda cada `apply_frame`, en tiempo virtual.
    * `failure` — la siguiente escritura lanza esa excepcion.
    * `on_frame` — gancho antes de registrar el fotograma `n`. Es lo que permite
      cancelar, desconectar o fallar en un punto exacto sin carreras.
    """

    def __init__(
        self,
        clock: ManualClock,
        *,
        latency_s: float = 0.0,
        capabilities: DeviceCapabilities = SINGLE_COLOR_STRIP,
        connected: bool = True,
    ) -> None:
        self._clock = clock
        self._capabilities = capabilities
        self._connected = connected
        self.latency_s = latency_s
        self.failure: Exception | None = None
        self.on_frame: Callable[[int], Awaitable[None]] | None = None
        self.frames: list[LightFrame] = []
        self.operations: list[str] = []

    @property
    def capabilities(self) -> DeviceCapabilities:
        return self._capabilities

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self, target: DeviceTarget) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def set_power(self, value: bool) -> None:
        self.operations.append(f"set_power:{value}")

    async def set_color(self, red: int, green: int, blue: int) -> None:
        self.operations.append(f"set_color:{red},{green},{blue}")

    async def set_brightness(self, brightness: int) -> None:
        self.operations.append(f"set_brightness:{brightness}")

    async def apply_frame(self, frame: LightFrame) -> None:
        if self.on_frame is not None:
            await self.on_frame(len(self.frames))
        if self.failure is not None:
            raise self.failure

        self._clock.advance(self.latency_s)
        self.frames.append(frame)
        self.operations.append(f"apply_frame:{frame.color.to_hex()}@{frame.brightness}")

    @property
    def colors(self) -> list[str]:
        return [frame.color.to_hex() for frame in self.frames]

    @property
    def brightnesses(self) -> list[int]:
        return [frame.brightness for frame in self.frames]


class InMemoryEffectRepository:
    """Doble de `EffectRepository`. Misma semantica de identidad que SQLite.

    `upsert` resuelve solo por `id` -- un efecto no tiene identidad fisica
    alternativa -- y `delete` devuelve `False` cuando no habia nada que borrar,
    que es lo que permite al caso de uso decidir el 404.
    """

    def __init__(self, effects: Sequence[EffectDefinition] = ()) -> None:
        self.effects: dict[UUID, EffectDefinition] = {effect.id: effect for effect in effects}

    def get(self, effect_id: UUID) -> EffectDefinition | None:
        return self.effects.get(effect_id)

    def list_all(self) -> Sequence[EffectDefinition]:
        return sorted(self.effects.values(), key=lambda effect: effect.name)

    def upsert(self, effect: EffectDefinition) -> EffectDefinition:
        self.effects[effect.id] = effect
        return effect

    def delete(self, effect_id: UUID) -> bool:
        return self.effects.pop(effect_id, None) is not None


class InMemorySceneRepository:
    """Doble de `SceneRepository` con la MISMA semantica que el de SQLModel.

    `get_activation` reproduce lo que hace el JOIN real: devuelve `None` si la
    escena no existe y una activacion con `targets` vacio si existe pero no tiene
    ningun objetivo habilitado. Un doble que confundiera los dos casos dejaria
    pasar un servicio que responde 404 donde debe responder 409.

    Los efectos se inyectan aparte porque en la base los aporta el JOIN, no la
    escena: un objetivo que apunte a un efecto que no esta aqui es un fallo del
    test, no un caso que el repositorio real pueda producir (lo impide la clave
    foranea).
    """

    def __init__(
        self,
        scenes: Sequence[Scene] = (),
        *,
        effects: Sequence[EffectDefinition] = (),
    ) -> None:
        self.scenes: dict[UUID, Scene] = {scene.id: scene for scene in scenes}
        self.effects: dict[UUID, EffectDefinition] = {effect.id: effect for effect in effects}

    def get(self, scene_id: UUID) -> Scene | None:
        return self.scenes.get(scene_id)

    def list_all(self) -> Sequence[Scene]:
        return sorted(self.scenes.values(), key=lambda scene: scene.name)

    def get_activation(self, scene_id: UUID) -> SceneActivation | None:
        scene = self.scenes.get(scene_id)
        if scene is None:
            return None

        return SceneActivation(
            scene=scene,
            targets=tuple(
                SceneTargetEffect(target=target, effect=self.effects[target.effect_id])
                for target in scene.enabled_targets
            ),
        )

    def upsert(self, scene: Scene) -> Scene:
        self.scenes[scene.id] = scene
        return scene

    def delete(self, scene_id: UUID) -> bool:
        return self.scenes.pop(scene_id, None) is not None


class InMemoryProfileRepository:
    """Doble de `ProfileRepository`. Misma semantica de identidad que SQLite."""

    def __init__(self, profiles: Sequence[Profile] = ()) -> None:
        self.profiles: dict[UUID, Profile] = {profile.id: profile for profile in profiles}

    def get(self, profile_id: UUID) -> Profile | None:
        return self.profiles.get(profile_id)

    def list_all(self) -> Sequence[Profile]:
        return sorted(self.profiles.values(), key=lambda profile: profile.name)

    def upsert(self, profile: Profile) -> Profile:
        self.profiles[profile.id] = profile
        return profile

    def delete(self, profile_id: UUID) -> bool:
        return self.profiles.pop(profile_id, None) is not None


class RecordingSceneActivator:
    """Doble de `SceneActivator`: anota que escenas se le pidio activar.

    Es lo que permite probar que el servicio de perfiles **delega** en vez de
    reimplementar la activacion: si algun dia construyera planes por su cuenta,
    esta lista se quedaria vacia.
    """

    def __init__(self) -> None:
        self.activated: list[UUID] = []

    async def activate(self, scene_id: UUID) -> SceneStatus:
        self.activated.append(scene_id)
        return SceneStatus(id=scene_id)
