"""Rutas de dispositivos: listar, escanear, registrar, conectar y desconectar.

El router es una traduccion HTTP y nada mas: no conoce Bleak, no abre sesiones
de SQLModel y no decide reglas. Todo lo que decide algo vive en
`application/device_service.py`.

Las operaciones sincronas del caso de uso (las que consultan el repositorio) se
lanzan con `run_in_threadpool`. La ruta es `async`, asi que sin eso la consulta a
SQLite correria EN el bucle de eventos y, con `PRAGMA busy_timeout=5000`, un
escritor concurrente lo congelaria hasta 5 s: sin escrituras BLE, sin difusion y
sin `/health`. Es la frontera correcta para hacerlo porque la capa de aplicacion
no puede importar Starlette sin invertir la direccion de las dependencias.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from backend.app.api.deps import DeviceServiceDep, ResourcesDep, ScanSlot, StoreDep
from backend.app.api.schemas.devices import (
    DeviceCreateRequest,
    DeviceRead,
    DiscoveredDeviceRead,
)
from backend.app.domain.state import GlobalState

router = APIRouter(prefix="/devices", tags=["devices"])


def _connected_id(state: GlobalState) -> UUID | None:
    """Cual de los dispositivos registrados ocupa el enlace, si es que hay alguno.

    El proceso mantiene UN enlace, asi que `GlobalState.device` es la respuesta
    completa: no hace falta preguntarle a cada dispositivo por separado (y
    hacerlo seria una consulta por fila).
    """
    status = state.device
    return status.device_id if status is not None and status.connected else None


@router.get("", summary="Dispositivos registrados")
async def list_devices(service: DeviceServiceDep, store: StoreDep) -> list[DeviceRead]:
    """Devuelve los dispositivos habilitados, con su estado de enlace.

    Los deshabilitados no se listan: `list_enabled` es lo que el puerto de
    repositorio ofrece, y un dispositivo deshabilitado no se puede conectar.
    """
    connected = _connected_id(await store.snapshot())
    devices = await run_in_threadpool(service.list_devices)
    return [DeviceRead.from_domain(device, connected=device.id == connected) for device in devices]


@router.get(
    "/scan",
    dependencies=[ScanSlot],
    summary="Buscar dispositivos cercanos",
)
async def scan_devices(
    service: DeviceServiceDep,
    # El parametro se llama `timeout` en el cable (README 16) y `timeout_s` en
    # Python: una funcion async con un parametro llamado `timeout` sugiere un
    # `asyncio.timeout` que aqui no aplica, y el linter lo señala.
    timeout_s: float | None = Query(
        default=None,
        alias="timeout",
        gt=0,
        description=(
            "Segundos de escaneo. Se recorta a LED_ROOM_BLE_SCAN_TIMEOUT: un cliente "
            "puede pedir menos tiempo, nunca mas."
        ),
    ),
) -> list[DiscoveredDeviceRead]:
    """Resultados efimeros: todavia no tienen id. Registrarlos es `POST /devices`."""
    discovered = await service.scan(timeout_s)
    return [DiscoveredDeviceRead.from_domain(device) for device in discovered]


@router.post("", status_code=201, summary="Registrar un dispositivo descubierto")
async def register_device(
    body: DeviceCreateRequest,
    service: DeviceServiceDep,
    resources: ResourcesDep,
    store: StoreDep,
) -> DeviceRead:
    """Convierte una direccion descubierta en un dispositivo con identidad.

    **Es idempotente por direccion**, y por eso no responde 409 ante un
    duplicado: el caso de uso resuelve la direccion ya registrada conservando su
    `id` (reescribirlo dejaria huerfanas las filas hijas) y, como mucho, la
    renombra. Un 409 obligaria a reimplementar aqui esa misma resolucion, con el
    riesgo de que las dos versiones dejen de coincidir.
    """
    # Se compara con la familia que DESCUBRE, que es la que etiqueta lo
    # registrado: un cliente que afirma `lotus_lantern` tras un escaneo BLE
    # tiene razon aunque el control siga en `null`.
    configured = resources.settings.discovery_adapter
    if body.adapter_type is not None and body.adapter_type != configured:
        raise ValueError(
            f"Este servicio descubre dispositivos {configured.value!r}: "
            f"no puede registrar un dispositivo {body.adapter_type.value!r}."
        )

    device = await run_in_threadpool(service.register, body.to_domain(), name=body.name)
    connected = _connected_id(await store.snapshot())
    return DeviceRead.from_domain(device, connected=device.id == connected)


@router.get("/{device_id}", summary="Estado de un dispositivo")
async def get_device(device_id: UUID, service: DeviceServiceDep, store: StoreDep) -> DeviceRead:
    device = await run_in_threadpool(service.get_device, device_id)
    connected = _connected_id(await store.snapshot())
    return DeviceRead.from_domain(device, connected=device.id == connected)


@router.post("/{device_id}/connect", summary="Abrir el enlace con el dispositivo")
async def connect_device(device_id: UUID, service: DeviceServiceDep) -> DeviceRead:
    """Conecta y reconcilia el hardware con el ultimo estado deseado."""
    status = await service.connect(device_id)
    device = await run_in_threadpool(service.get_device, device_id)
    return DeviceRead.from_domain(device, connected=status.connected)


@router.post("/{device_id}/disconnect", summary="Cerrar el enlace con el dispositivo")
async def disconnect_device(device_id: UUID, service: DeviceServiceDep) -> DeviceRead:
    """**Idempotente**: desconectar lo ya desconectado responde 200 sin efectos."""
    status = await service.disconnect(device_id)
    device = await run_in_threadpool(service.get_device, device_id)
    return DeviceRead.from_domain(device, connected=status.connected)
