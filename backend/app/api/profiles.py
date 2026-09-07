"""Rutas de perfiles: catalogo y activacion.

Mismo reparto que en escenas: el router traduce HTTP y `application/
profile_service.py` decide. La activacion no se implementa aqui ni alli: se
delega en el servicio de escenas.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Response
from starlette.concurrency import run_in_threadpool

from backend.app.api.deps import ProfileServiceDep
from backend.app.api.schemas.profiles import ProfileActivationRead, ProfileRead, ProfileWrite

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", summary="Catalogo de perfiles")
async def list_profiles(service: ProfileServiceDep) -> list[ProfileRead]:
    profiles = await run_in_threadpool(service.list_profiles)
    return [ProfileRead.from_domain(profile) for profile in profiles]


@router.post("", status_code=201, summary="Crear un perfil")
async def create_profile(body: ProfileWrite, service: ProfileServiceDep) -> ProfileRead:
    """El `id` lo genera el SERVIDOR. Una escena inexistente responde 422."""
    profile = await run_in_threadpool(service.save, body.to_domain(uuid4()))
    return ProfileRead.from_domain(profile)


@router.get("/{profile_id}", summary="Un perfil")
async def get_profile(profile_id: UUID, service: ProfileServiceDep) -> ProfileRead:
    profile = await run_in_threadpool(service.get_profile, profile_id)
    return ProfileRead.from_domain(profile)


@router.put("/{profile_id}", summary="Reemplazar un perfil")
async def replace_profile(
    profile_id: UUID,
    body: ProfileWrite,
    service: ProfileServiceDep,
) -> ProfileRead:
    """Reemplazo completo, escenas incluidas. 404 si el perfil no existe."""
    await run_in_threadpool(service.get_profile, profile_id)
    profile = await run_in_threadpool(service.save, body.to_domain(profile_id))
    return ProfileRead.from_domain(profile)


@router.delete("/{profile_id}", status_code=204, summary="Borrar un perfil")
async def delete_profile(profile_id: UUID, service: ProfileServiceDep) -> Response:
    """Borra el perfil y sus enlaces. Las escenas se conservan: son catalogo."""
    await run_in_threadpool(service.delete, profile_id)
    return Response(status_code=204)


@router.post("/{profile_id}/activate", summary="Activar un perfil")
async def activate_profile(
    profile_id: UUID,
    service: ProfileServiceDep,
) -> ProfileActivationRead:
    """Activa la escena predeterminada del perfil; difunde `scene.activated`.

    Errores posibles: `404` si el perfil no existe, `409` si no tiene ninguna
    escena, y todos los de activar una escena -- son los mismos porque es la
    misma operacion.
    """
    status = await service.activate(profile_id)
    return ProfileActivationRead.from_domain(profile_id, status)
