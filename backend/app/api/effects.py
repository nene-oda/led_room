"""Rutas de efectos: catalogo y reproduccion.

El router es traduccion HTTP y nada mas: no genera fotogramas, no toca el
adaptador y no decide reglas. Todo lo que decide algo vive en
`application/effect_service.py` y en `domain/effects/`.

Las operaciones que hacen `commit()` se lanzan con `run_in_threadpool`: la ruta
es `async`, asi que sin eso la escritura en SQLite correria EN el bucle de
eventos y, con `PRAGMA busy_timeout=5000`, un escritor concurrente lo congelaria
hasta 5 s -- sin escrituras BLE, sin difusion y sin `/health`.

**Reproducir no persiste nada.** `start` lee una fila y a partir de ahi el motor
genera fotogramas en memoria: cero escrituras por fotograma (ARCHITECTURE 4.5).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Response
from starlette.concurrency import run_in_threadpool

from backend.app.api.deps import EffectServiceDep, StoreDep
from backend.app.api.schemas.effects import EffectRead, EffectWrite
from backend.app.api.schemas.state import EffectStatusRead

router = APIRouter(prefix="/effects", tags=["effects"])


@router.get("", summary="Catalogo de efectos")
async def list_effects(service: EffectServiceDep) -> list[EffectRead]:
    effects = await run_in_threadpool(service.list_effects)
    return [EffectRead.from_domain(effect) for effect in effects]


@router.post("", status_code=201, summary="Crear un efecto")
async def create_effect(body: EffectWrite, service: EffectServiceDep) -> EffectRead:
    """El `id` lo genera el SERVIDOR.

    Igual que con los dispositivos: el cliente no puede inventar la identidad de
    algo que todavia no existe, y dejarselo elegir abriria la puerta a que dos
    clientes colisionen.
    """
    effect = await run_in_threadpool(service.save, body.to_domain(uuid4()))
    return EffectRead.from_domain(effect)


@router.get("/{effect_id}", summary="Un efecto")
async def get_effect(effect_id: UUID, service: EffectServiceDep) -> EffectRead:
    effect = await run_in_threadpool(service.get_effect, effect_id)
    return EffectRead.from_domain(effect)


@router.put("/{effect_id}", summary="Reemplazar un efecto")
async def replace_effect(
    effect_id: UUID,
    body: EffectWrite,
    service: EffectServiceDep,
) -> EffectRead:
    """Reemplazo completo, pasos incluidos. 404 si el efecto no existe.

    Se comprueba la existencia antes de escribir para que un `PUT` sobre un id
    inventado no cree un efecto por la puerta de atras, con un id que el cliente
    eligio.
    """
    await run_in_threadpool(service.get_effect, effect_id)
    effect = await run_in_threadpool(service.save, body.to_domain(effect_id))
    return EffectRead.from_domain(effect)


@router.delete("/{effect_id}", status_code=204, summary="Borrar un efecto")
async def delete_effect(effect_id: UUID, service: EffectServiceDep) -> Response:
    await run_in_threadpool(service.delete, effect_id)
    return Response(status_code=204)


@router.post("/{effect_id}/start", summary="Reproducir un efecto")
async def start_effect(effect_id: UUID, service: EffectServiceDep) -> EffectStatusRead:
    """Sustituye lo que estuviera sonando; difunde `effect.started`.

    Errores posibles, todos resueltos ANTES de la primera escritura al
    dispositivo: `404` si el efecto no existe, `409` si no hay enlace o si al
    dispositivo le falta una capacidad dura, y `422` si el efecto no tiene los
    pasos que su algoritmo necesita.
    """
    status = await service.start(effect_id)
    return EffectStatusRead.from_domain(status)


@router.post("/{effect_id}/stop", summary="Detener un efecto")
async def stop_effect(
    effect_id: UUID,
    service: EffectServiceDep,
    store: StoreDep,
) -> EffectStatusRead | None:
    """**Idempotente**: parar algo que ya no suena responde 200 con `null`.

    Devuelve lo que suena DESPUES de la llamada, no un `null` fijo: parar por id
    un efecto al que ya sustituyo otro no para nada, y responder `null` mentiria
    sobre el estado global.

    El ultimo fotograma se queda puesto a proposito: apagar la luz al parar
    produciria un parpadeo negro al encadenar dos escenas (NEXT_STEPS 6.4).
    """
    await service.stop(effect_id)

    effect = (await store.snapshot()).effect
    return None if effect is None else EffectStatusRead.from_domain(effect)
