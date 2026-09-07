"""Dominio de escenas <-> filas de `scenes` y `scene_targets`.

Mismo papel que `mappers/effect.py`: por encima de este modulo solo circulan
tipos de dominio y por debajo solo `*Record`. Ningun servicio ni router conoce
el nombre de una columna (ARCHITECTURE 5.4).

A diferencia del mapper de efectos, aqui **no hay ningun `SceneMappingError`**:
las columnas de `scenes` y `scene_targets` son escalares, claves foraneas y
booleanos, sin ningun enumerado ni color que pueda estar corrupto en la base. Un
tipo de error que ninguna rama puede lanzar seria decoracion.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.app.domain.scenes.models import (
    Scene,
    SceneActivation,
    SceneTarget,
    SceneTargetEffect,
)
from backend.app.infrastructure.persistence.mappers.effect import effect_to_domain
from backend.app.infrastructure.persistence.models.base import utc_now
from backend.app.infrastructure.persistence.models.effect import EffectRecord
from backend.app.infrastructure.persistence.models.scene import SceneRecord, SceneTargetRecord


def scene_to_domain(record: SceneRecord) -> Scene:
    """Reconstruye la escena a partir de la fila y sus objetivos.

    Los objetivos se ordenan por `device_id`, y ordenarlos aqui **si** es
    correcto (a diferencia de los pasos de un efecto, que llegan ordenados por
    la relacion): `scene_targets` no declara ningun `order_by` y su clave
    primaria es un UUID aleatorio, asi que el orden de la base no significa nada.
    Sin este criterio, dos lecturas de la misma escena podrian devolver los
    objetivos en distinto orden.
    """
    return Scene(
        id=record.id,
        name=record.name,
        description=record.description,
        icon=record.icon,
        is_builtin=record.is_builtin,
        is_favorite=record.is_favorite,
        targets=tuple(target_to_domain(target) for target in _ordered(record.targets)),
    )


def target_to_domain(record: SceneTargetRecord) -> SceneTarget:
    return SceneTarget(
        device_id=record.device_id,
        effect_id=record.effect_id,
        brightness=record.brightness,
        speed=record.speed,
        enabled=record.enabled,
    )


def apply_scene_to_record(record: SceneRecord, scene: Scene) -> None:
    """Vuelca las columnas escalares de la escena sobre la fila.

    Los objetivos NO se tocan aqui: sustituirlos exige intercalar un `flush`
    entre los DELETE y los INSERT, y eso es semantica de sesion, que pertenece al
    repositorio (ver `target_records`).
    """
    record.name = scene.name
    record.description = scene.description
    record.icon = scene.icon
    record.is_builtin = scene.is_builtin
    record.is_favorite = scene.is_favorite
    record.updated_at = utc_now()


def target_records(record: SceneRecord, scene: Scene) -> list[SceneTargetRecord]:
    """Las filas de `scene_targets` que corresponden a esta escena.

    Se construyen nuevas, con un `id` nuevo, en vez de conciliar las existentes:
    el objetivo no tiene identidad propia para el usuario -- la clave real es
    `(scene, device)` -- y nadie lo referencia desde otra tabla. Es la misma
    decision que con los pasos de un efecto, y por el mismo motivo.
    """
    return [
        SceneTargetRecord(
            scene_id=record.id,
            device_id=target.device_id,
            effect_id=target.effect_id,
            brightness=target.brightness,
            speed=target.speed,
            enabled=target.enabled,
        )
        for target in scene.targets
    ]


def activation_to_domain(
    record: SceneRecord,
    rows: Sequence[tuple[SceneTargetRecord, EffectRecord]],
) -> SceneActivation:
    """Compone la escena con los objetivos habilitados y sus efectos.

    `rows` llega de una sola consulta con JOIN: emparejar aqui es traduccion, no
    acceso a datos, y por eso el repositorio no construye modelos de dominio a
    mano.
    """
    return SceneActivation(
        scene=scene_to_domain(record),
        targets=tuple(
            SceneTargetEffect(target=target_to_domain(target), effect=effect_to_domain(effect))
            for target, effect in rows
        ),
    )


def _ordered(targets: Sequence[SceneTargetRecord]) -> list[SceneTargetRecord]:
    return sorted(targets, key=lambda target: target.device_id)
