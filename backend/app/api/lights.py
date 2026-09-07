"""Rutas de control de la luz.

**No llevan `device_id`**: el contrato del README 16 esta congelado sin el y el
proceso mantiene UN enlace. Resolver "cual" no es trabajo de esta capa:

* con cero dispositivos conectados, `LightService` lanza
  `DeviceNotConnectedError` y la politica de errores responde 409;
* "mas de uno conectado" no es representable: `GlobalState.device` es una sola
  ranura y `DeviceService` rechaza con 409 (`device_busy`) el intento de abrir
  un segundo enlace. El caso se ataja al conectar, no aqui.

Asi se evita inventar una columna `is_default` y su migracion.

**Aqui se cierra la politica de persistencia del estado deseado** (NEXT_STEPS
A3): una peticion HTTP es, por definicion, una intencion deliberada del usuario,
asi que es el sitio correcto para escribir en la base. El WebSocket, que
transporta el arrastre del selector, no persiste nada.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from backend.app.api.deps import (
    LightServiceDep,
    RepositoryDep,
    StoreDep,
    ThrottlesDep,
)
from backend.app.api.schemas.lights import (
    BrightnessRequest,
    ColorRequest,
    LightStateRead,
    PowerRequest,
)
from backend.app.application.state_store import StateStore
from backend.app.domain.devices.repositories import DeviceRepository
from backend.app.domain.lighting import LightState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lights", tags=["lights"])


async def _remember(repository: DeviceRepository, store: StateStore, state: LightState) -> None:
    """Persiste el estado deseado del dispositivo conectado.

    Se llama una vez por peticion, jamas por fotograma: durante un arrastre o un
    efecto no se escribe nada en la base.

    Un fallo al guardar **no** convierte en error la peticion. SQLite es la cache
    de arranque, no la fuente de verdad (NEXT_STEPS A4): el hardware ya aplico el
    cambio y el estado autoritativo en memoria ya lo refleja. Devolver 500 le
    diria al cliente que su comando fracaso cuando lo unico que se perdio es que
    sobreviva a un reinicio.

    Va al threadpool porque `save_state` hace `commit()`: con `PRAGMA
    busy_timeout=5000`, un escritor concurrente congelaria el bucle de eventos
    hasta 5 s -- sin escrituras BLE, sin difusion y sin `/health`. Que la
    dependencia de la sesion sea sincrona solo saca del bucle el abrir y cerrar
    la `Session`, no las consultas.
    """
    device = (await store.snapshot()).device
    if device is None:
        return

    try:
        await run_in_threadpool(repository.save_state, device.device_id, state)
    except Exception:
        logger.exception("No se pudo persistir el estado deseado de %s", device.device_id)


@router.post("/power", summary="Encender o apagar")
async def set_power(
    body: PowerRequest,
    service: LightServiceDep,
    throttles: ThrottlesDep,
    repository: RepositoryDep,
    store: StoreDep,
) -> LightStateRead:
    """Un comando deliberado cancela los arrastres en curso y toma el control.

    Sin esto, un color o un brillo pendiente del limitador podria aplicarse
    DESPUES del apagado y volver a encender la tira.
    """
    await throttles.cancel_all()
    state = await service.set_power(body.on)
    await _remember(repository, store, state)
    return LightStateRead.from_domain(state)


@router.put("/color", summary="Fijar el color")
async def set_color(
    body: ColorRequest,
    service: LightServiceDep,
    throttles: ThrottlesDep,
    repository: RepositoryDep,
    store: StoreDep,
) -> LightStateRead:
    """Fija un color concreto. Es el cierre de un gesto, no el gesto entero.

    El arrastre viaja por `/ws` (`light.color`), que si esta limitado a ~20
    actualizaciones por segundo. Esta ruta aplica el valor directamente y
    cancela el limitador del color -- solo ese: el brillo es otro campo y su
    arrastre no queda invalidado por fijar un color.
    """
    await throttles.color.cancel()
    state = await service.set_color(body.to_domain())
    await _remember(repository, store, state)
    return LightStateRead.from_domain(state)


@router.put("/brightness", summary="Fijar el brillo")
async def set_brightness(
    body: BrightnessRequest,
    service: LightServiceDep,
    throttles: ThrottlesDep,
    repository: RepositoryDep,
    store: StoreDep,
) -> LightStateRead:
    """Fija el brillo y cancela su propio arrastre, no el del color."""
    await throttles.brightness.cancel()
    state = await service.set_brightness(body.brightness)
    await _remember(repository, store, state)
    return LightStateRead.from_domain(state)
