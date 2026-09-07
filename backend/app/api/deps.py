"""Cableado de la frontera HTTP: como llega cada ruta a lo que necesita.

Dos vidas distintas, y la diferencia importa:

* **Larga vida** — engine, adaptador, descubridor, estado global, `LightService`
  y los limitadores de arrastre. Se construyen UNA vez en el `lifespan` y viven
  en `app.state` dentro de `AppResources`. Los limitadores, en particular, no
  pueden reconstruirse por peticion: perderian el valor pendiente del arrastre.
* **Vida corta** — la `Session` de SQLModel, su repositorio y el `DeviceService`
  que los usa. Se construyen por peticion y mueren con ella.

La `Session` es SINCRONA a proposito y no se convierte a `AsyncSession`
(NEXT_STEPS 4.5). Ojo con lo que eso significa exactamente: FastAPI ejecuta en el
threadpool **esta dependencia**, es decir abrir y cerrar la sesion, pero NO las
consultas, que las hace la ruta -- que si es `async` -- y por tanto corren en el
bucle de eventos. Con `PRAGMA busy_timeout=5000`, un escritor concurrente podria
congelar el bucle entero hasta 5 s: sin escrituras BLE, sin difusion y sin
`/health`. Por eso las rutas envuelven cada llamada al repositorio en
`run_in_threadpool`.

`AppResources` es un contenedor tipado en vez de atributos sueltos en
`app.state`: `State.__getattr__` devuelve `Any`, asi que sin el, cada acceso
seria un agujero para mypy y un nombre magico repetido en cada modulo.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlmodel import Session
from starlette.applications import Starlette

from backend.app.application.device_service import DeviceService
from backend.app.application.effect_service import EffectPlayer, EffectService
from backend.app.application.errors import DeviceBusyError
from backend.app.application.light_service import LightService
from backend.app.application.profile_service import ProfileService
from backend.app.application.scene_service import SceneService
from backend.app.application.state_store import StateStore
from backend.app.application.throttle import LightThrottles
from backend.app.config import Settings
from backend.app.domain.devices.ports import DeviceDiscoveryPort, LightDevicePort
from backend.app.domain.devices.repositories import DeviceRepository
from backend.app.domain.effects.repositories import EffectRepository
from backend.app.domain.profiles.repositories import ProfileRepository
from backend.app.domain.scenes.repositories import SceneRepository
from backend.app.infrastructure.persistence.database import session_factory
from backend.app.infrastructure.persistence.repositories import (
    SQLModelDeviceRepository,
    SQLModelEffectRepository,
    SQLModelProfileRepository,
    SQLModelSceneRepository,
)
from backend.app.websocket.manager import ConnectionManager


@dataclass(frozen=True, slots=True)
class AppResources:
    """Todo lo de larga vida, construido en el `lifespan` y solo ahi."""

    settings: Settings
    engine: Engine
    light_device: LightDevicePort
    discovery: DeviceDiscoveryPort

    #: Si el adaptador configurado puede encontrar hardware (lo declara
    #: `AdapterRegistration`, unico sitio donde se dice). Se resuelve en el
    #: `lifespan`, como el resto de la eleccion de adaptador, para que las rutas
    #: no tengan que consultar el registro de infraestructura.
    supports_discovery: bool

    store: StateStore
    light: LightService
    throttles: LightThrottles
    connections: ConnectionManager

    #: Titular del unico bucle de efectos del proceso. De larga vida porque el
    #: bucle sobrevive a la peticion que lo arranco, y porque `LightService` lo
    #: usa como funcion de preempcion en cada comando manual.
    effects: EffectPlayer

    #: Estado de proceso, no de dominio: `GET /devices/scan` responde 409 si ya
    #: hay uno en curso. Vive aqui y no dentro de `DeviceService` porque el
    #: servicio es de vida corta (uno nuevo por peticion) y no podria recordar
    #: nada entre dos llamadas.
    scan_lock: asyncio.Lock


def resources_of(app: Starlette) -> AppResources:
    """Recupera el contenedor con un error legible si el `lifespan` no corrio.

    Sin esta comprobacion, un `TestClient` usado sin su gestor de contexto
    fallaria con un `AttributeError` sobre `app.state` a mitad de una ruta.
    """
    resources = getattr(app.state, "resources", None)
    if not isinstance(resources, AppResources):
        raise RuntimeError(
            "Las dependencias de larga vida no estan construidas: el lifespan de "
            "la aplicacion no se ha ejecutado."
        )
    return resources


def get_resources(request: Request) -> AppResources:
    return resources_of(request.app)


ResourcesDep = Annotated[AppResources, Depends(get_resources)]


def get_settings_dep(resources: ResourcesDep) -> Settings:
    return resources.settings


def get_store(resources: ResourcesDep) -> StateStore:
    return resources.store


def get_light_service(resources: ResourcesDep) -> LightService:
    return resources.light


def get_throttles(resources: ResourcesDep) -> LightThrottles:
    return resources.throttles


def get_discovery(resources: ResourcesDep) -> DeviceDiscoveryPort:
    """Puerto de descubrimiento.

    Se expone como dependencia propia, y no se lee de `AppResources` alli donde
    hace falta, para que un test lo sustituya con `dependency_overrides` sin
    tocar el resto del cableado.
    """
    return resources.discovery


def get_session(resources: ResourcesDep) -> Iterator[Session]:
    """Sesion por peticion. Generador SINCRONO: corre en el threadpool."""
    yield from session_factory(resources.engine)


SessionDep = Annotated[Session, Depends(get_session)]


def get_effect_player(resources: ResourcesDep) -> EffectPlayer:
    return resources.effects


def get_device_repository(session: SessionDep) -> DeviceRepository:
    """Devuelve el PUERTO de dominio, no la implementacion.

    Asi mypy comprueba en cada ruta que solo se usa lo que el puerto promete.
    """
    return SQLModelDeviceRepository(session)


def get_effect_repository(session: SessionDep) -> EffectRepository:
    """Devuelve el PUERTO de dominio, no la implementacion."""
    return SQLModelEffectRepository(session)


def get_scene_repository(session: SessionDep) -> SceneRepository:
    """Devuelve el PUERTO de dominio, no la implementacion."""
    return SQLModelSceneRepository(session)


def get_profile_repository(session: SessionDep) -> ProfileRepository:
    """Devuelve el PUERTO de dominio, no la implementacion."""
    return SQLModelProfileRepository(session)


RepositoryDep = Annotated[DeviceRepository, Depends(get_device_repository)]
EffectRepositoryDep = Annotated[EffectRepository, Depends(get_effect_repository)]
SceneRepositoryDep = Annotated[SceneRepository, Depends(get_scene_repository)]
ProfileRepositoryDep = Annotated[ProfileRepository, Depends(get_profile_repository)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
StoreDep = Annotated[StateStore, Depends(get_store)]
LightServiceDep = Annotated[LightService, Depends(get_light_service)]
ThrottlesDep = Annotated[LightThrottles, Depends(get_throttles)]
DiscoveryDep = Annotated[DeviceDiscoveryPort, Depends(get_discovery)]
EffectPlayerDep = Annotated[EffectPlayer, Depends(get_effect_player)]


def build_device_service(
    *,
    repository: DeviceRepository,
    discovery: DeviceDiscoveryPort,
    resources: AppResources,
) -> DeviceService:
    """Compone el caso de uso de dispositivos.

    Funcion aparte de la dependencia porque el arranque degradado del `lifespan`
    necesita exactamente el mismo servicio y no hay ninguna peticion HTTP de la
    que colgarlo.
    """
    return DeviceService(
        repository=repository,
        discovery=discovery,
        device=resources.light_device,
        store=resources.store,
        # La familia con la que se ETIQUETA lo registrado es la que lo
        # descubrio, no la que controla: si el escaner BLE encontro la tira, la
        # tira es BLE aunque este proceso todavia no sepa escribirle. Guardarla
        # como `null` la dejaria mal etiquetada para siempre, porque
        # `get_by_address` resuelve solo por direccion y `POST /devices` es
        # idempotente: la fila equivocada se reutilizaria en cada alta posterior.
        adapter_type=resources.settings.discovery_adapter,
        scan_timeout_s=resources.settings.ble_scan_timeout,
    )


def get_effect_service(
    resources: ResourcesDep,
    repository: EffectRepositoryDep,
    player: EffectPlayerDep,
) -> EffectService:
    """Compone el caso de uso de efectos.

    Las capacidades salen del adaptador construido en el `lifespan`, que es
    quien las declara, y el tope de fps de la configuracion: el efecto pide
    suavidad y el despliegue pone el limite (`min(effect.fps, effect_fps)`).
    """
    return EffectService(
        repository=repository,
        player=player,
        capabilities=resources.light_device.capabilities,
        max_fps=resources.settings.effect_fps,
    )


EffectServiceDep = Annotated[EffectService, Depends(get_effect_service)]


def get_scene_service(
    resources: ResourcesDep,
    repository: SceneRepositoryDep,
    player: EffectPlayerDep,
) -> SceneService:
    """Compone el caso de uso de escenas.

    Recibe lo MISMO que `EffectService` (capacidades del adaptador, tope de fps y
    el unico reproductor del proceso) porque activar una escena es reproducir
    efectos: si aqui se construyera un reproductor propio, habria dos bucles
    escribiendo sobre la misma tira.
    """
    return SceneService(
        repository=repository,
        player=player,
        store=resources.store,
        capabilities=resources.light_device.capabilities,
        max_fps=resources.settings.effect_fps,
    )


SceneServiceDep = Annotated[SceneService, Depends(get_scene_service)]


def get_profile_service(
    repository: ProfileRepositoryDep,
    scenes: SceneServiceDep,
) -> ProfileService:
    """Compone el caso de uso de perfiles sobre el de escenas.

    La dependencia va en esta direccion y no al reves: un perfil elige una escena
    y delega, mientras que una escena no sabe que existen los perfiles.
    """
    return ProfileService(repository=repository, scenes=scenes)


ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]


def get_device_service(
    resources: ResourcesDep,
    repository: RepositoryDep,
    discovery: DiscoveryDep,
) -> DeviceService:
    return build_device_service(repository=repository, discovery=discovery, resources=resources)


DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]


async def scan_slot(resources: ResourcesDep) -> AsyncIterator[None]:
    """Reserva el unico turno de escaneo del proceso; 409 si ya esta ocupado.

    Se comprueba y se toma el cerrojo sin ningun `await` entre medias, asi que
    en un bucle de eventos no hay carrera posible. Se responde 409 en vez de
    esperar turno: dos escaneos encolados harian que el segundo cliente esperase
    el doble del timeout sin saber por que.

    Reutiliza `DeviceBusyError` (409, `device_busy`) en lugar de inventar un
    codigo nuevo: para el cliente el hecho es el mismo, el recurso esta ocupado.
    """
    lock = resources.scan_lock
    if lock.locked():
        raise DeviceBusyError("Ya hay un escaneo de dispositivos en curso; espera a que termine.")

    async with lock:
        yield


ScanSlot = Depends(scan_slot)
