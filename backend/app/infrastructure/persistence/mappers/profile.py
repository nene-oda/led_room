"""Dominio de perfiles <-> filas de `profiles` y `profile_scenes`.

Mismo papel y misma ausencia de `MappingError` que `mappers/scene.py`: las
columnas son escalares y claves foraneas, sin enumerados que puedan estar
corruptos.

El orden de las escenas lo declara la relacion (`order_by` por `position`), asi
que aqui no se reordena: seria una segunda fuente de verdad para el mismo orden.
Que dos escenas empatadas en `position` se resuelvan de forma determinista es
responsabilidad del dominio (`Profile.default_scene_id`), no de la lectura.
"""

from __future__ import annotations

from backend.app.domain.profiles.models import Profile, ProfileScene
from backend.app.infrastructure.persistence.models.base import utc_now
from backend.app.infrastructure.persistence.models.profile import ProfileRecord, ProfileSceneRecord


def profile_to_domain(record: ProfileRecord) -> Profile:
    return Profile(
        id=record.id,
        name=record.name,
        description=record.description,
        icon=record.icon,
        is_builtin=record.is_builtin,
        scenes=tuple(_link_to_domain(link) for link in record.scene_links),
    )


def apply_profile_to_record(record: ProfileRecord, profile: Profile) -> None:
    """Vuelca las columnas escalares del perfil sobre la fila.

    `profiles.is_default` **no se toca**: marcar "el perfil predeterminado" es un
    invariante entre filas (solo puede haber uno) que hoy no tiene ningun caso de
    uso propietario -- no existe ninguna ruta que active "el perfil por defecto".
    Escribirlo sin nadie que garantice la unicidad crearia un segundo concepto de
    "predeterminado" conviviendo con el de las escenas del perfil.
    """
    record.name = profile.name
    record.description = profile.description
    record.icon = profile.icon
    record.is_builtin = profile.is_builtin
    record.updated_at = utc_now()


def scene_link_records(record: ProfileRecord, profile: Profile) -> list[ProfileSceneRecord]:
    """Las filas de `profile_scenes` que corresponden a este perfil."""
    return [
        ProfileSceneRecord(
            profile_id=record.id,
            scene_id=link.scene_id,
            position=link.position,
            is_default=link.is_default,
        )
        for link in profile.scenes
    ]


def _link_to_domain(record: ProfileSceneRecord) -> ProfileScene:
    return ProfileScene(
        scene_id=record.scene_id,
        position=record.position,
        is_default=record.is_default,
    )
