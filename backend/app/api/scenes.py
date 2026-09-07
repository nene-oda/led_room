"""Rutas de escenas: catalogo y activacion.

El router es traduccion HTTP y nada mas: no construye planes, no cancela bucles y
no decide que se puede reproducir. Todo eso vive en
`application/scene_service.py` y en `domain/scenes/`.

Las operaciones que consultan la base se lanzan con `run_in_threadpool`: la ruta
es `async`, asi que sin eso la escritura en SQLite correria EN el bucle de
eventos y, con `PRAGMA busy_timeout=5000`, un escritor concurrente lo congelaria
hasta 5 s -- sin escrituras BLE, sin difusion y sin `/health`.

**Activar no persiste nada.** La escena se lee una vez y a partir de ahi el motor
genera fotogramas en memoria: cero escrituras por fotograma (ARCHITECTURE 4.5).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Response
from starlette.concurrency import run_in_threadpool

from backend.app.api.deps import SceneServiceDep
from backend.app.api.schemas.scenes import SceneDuplicateRequest, SceneRead, SceneWrite
from backend.app.api.schemas.state import SceneStatusRead

router = APIRouter(prefix="/scenes", tags=["scenes"])


@router.get("", summary="Catalogo de escenas")
async def list_scenes(service: SceneServiceDep) -> list[SceneRead]:
    scenes = await run_in_threadpool(service.list_scenes)
    return [SceneRead.from_domain(scene) for scene in scenes]


@router.post("", status_code=201, summary="Crear una escena")
async def create_scene(body: SceneWrite, service: SceneServiceDep) -> SceneRead:
    """El `id` lo genera el SERVIDOR, igual que con dispositivos y efectos.

    Un objetivo que apunte a un dispositivo o a un efecto inexistente responde
    422: lo detecta la clave foranea, que es la unica que puede saberlo sin una
    consulta extra por objetivo.
    """
    scene = await run_in_threadpool(service.save, body.to_domain(uuid4()))
    return SceneRead.from_domain(scene)


@router.get("/{scene_id}", summary="Una escena")
async def get_scene(scene_id: UUID, service: SceneServiceDep) -> SceneRead:
    scene = await run_in_threadpool(service.get_scene, scene_id)
    return SceneRead.from_domain(scene)


@router.put("/{scene_id}", summary="Reemplazar una escena")
async def replace_scene(
    scene_id: UUID,
    body: SceneWrite,
    service: SceneServiceDep,
) -> SceneRead:
    """Reemplazo completo, objetivos incluidos. 404 si la escena no existe.

    Se comprueba la existencia antes de escribir para que un `PUT` sobre un id
    inventado no cree una escena por la puerta de atras, con un id que el cliente
    eligio.
    """
    await run_in_threadpool(service.get_scene, scene_id)
    scene = await run_in_threadpool(service.save, body.to_domain(scene_id))
    return SceneRead.from_domain(scene)


@router.post("/{scene_id}/duplicate", status_code=201, summary="Duplicar una escena")
async def duplicate_scene(
    scene_id: UUID,
    service: SceneServiceDep,
    body: SceneDuplicateRequest | None = None,
) -> SceneRead:
    """Copia la escena con identidad nueva. El cuerpo es opcional."""
    scene = await run_in_threadpool(
        service.duplicate, scene_id, name=None if body is None else body.name
    )
    return SceneRead.from_domain(scene)


@router.delete("/{scene_id}", status_code=204, summary="Borrar una escena")
async def delete_scene(scene_id: UUID, service: SceneServiceDep) -> Response:
    """Los objetivos se van en cascada; los efectos que usaba, no: son catalogo."""
    await run_in_threadpool(service.delete, scene_id)
    return Response(status_code=204)


@router.post("/{scene_id}/activate", summary="Activar una escena")
async def activate_scene(scene_id: UUID, service: SceneServiceDep) -> SceneStatusRead:
    """Reproduce la escena entera o no reproduce nada; difunde `scene.activated`.

    Errores posibles, **todos resueltos antes de la primera escritura al
    dispositivo**: `404` si la escena no existe, `409` si no hay enlace, si algun
    objetivo apunta a otro dispositivo, si la escena no tiene objetivos
    habilitados o si al dispositivo le falta una capacidad dura, y `422` si algun
    efecto no tiene los pasos que su algoritmo necesita.
    """
    status = await service.activate(scene_id)
    return SceneStatusRead.from_domain(status)
