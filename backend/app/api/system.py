"""`GET /system`: descripcion estatica del servidor (adaptador y descubrimiento).

Ruta propia y no un campo mas de `GET /state` ni de `/health`:

* `/state` describe **la habitacion** (enlace, luz, efecto, escena), es mutable,
  lleva `version` y su cuerpo es tambien el del frame `state.snapshot`, que se
  difunde por WebSocket. Esto de aqui no cambia mientras el proceso vive.
* `/health` es deliberadamente tonto porque alimenta el `HEALTHCHECK` del
  contenedor (ARCHITECTURE 7.5): no debe crecer con diagnosticos.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.deps import ResourcesDep
from backend.app.api.schemas.system import SystemInfoRead

router = APIRouter(tags=["system"])


@router.get("/system", summary="Capacidades de este servidor")
async def read_system(resources: ResourcesDep) -> SystemInfoRead:
    """Traduccion pura: todo esto se decidio al arrancar, aqui no se decide nada."""
    return SystemInfoRead(
        adapter_type=resources.settings.device_adapter,
        discovery_type=resources.settings.discovery_adapter,
        supports_discovery=resources.supports_discovery,
        scan_timeout_seconds=resources.settings.ble_scan_timeout,
    )
