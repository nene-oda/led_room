"""Dominio de efectos <-> filas de `effects` y `effect_steps`.

Existe por los mismos dos motivos que el mapper de dispositivos, ambos
verificados contra el codigo y no por simetria arquitectonica:

1. **Los tipos no coinciden.** `effects.type` y `effect_steps.easing` son texto
   libre en la base y enumerados en el dominio; `effect_steps.color_hex` es una
   cadena y `EffectStep.color` es un `RGBColor`. Traducir eso en el repositorio
   lo repartiria entre `get`, `list_all` y `upsert`.
2. **`min_brightness` y `max_brightness` son NULL-ables.** `NULL` significa "usa
   la envolvente por defecto del dominio", no "usa cero", y esa lectura tiene
   que estar en un unico sitio.

El color se serializa SIEMPRE con `RGBColor.to_hex()`, que emite MAYUSCULAS
(ARCHITECTURE 3.2). Hoy `effect_steps.color_hex` no tiene el `CHECK ... GLOB`
que si tiene `device_state`, pero escribir minusculas aqui produciria un
catalogo con dos formatos del mismo color.

**Ningun `LightFrame` pasa por aqui**: los fotogramas se generan en memoria y no
se persisten jamas (NEXT_STEPS 6.10).
"""

from __future__ import annotations

from backend.app.domain.effects.models import (
    Easing,
    EffectDefinition,
    EffectStep,
    EffectType,
)
from backend.app.domain.lighting import BRIGHTNESS_MAX, BRIGHTNESS_MIN, RGBColor
from backend.app.infrastructure.persistence.models.base import utc_now
from backend.app.infrastructure.persistence.models.effect import EffectRecord, EffectStepRecord


class EffectMappingError(Exception):
    """Una fila persistida no se puede traducir a dominio.

    NO hereda de `ValueError` a proposito: la politica de errores mapea los
    `ValueError` de rango a `422`, y una fila corrupta no es una peticion
    invalida del cliente sino un fallo del servidor (NEXT_STEPS A6).
    """


def effect_type_to_column(effect_type: EffectType) -> str:
    """Valor que se guarda en `effects.type`."""
    return effect_type.value


def effect_to_domain(record: EffectRecord) -> EffectDefinition:
    """Reconstruye la definicion a partir de la fila y sus pasos.

    Los pasos llegan ordenados por `position` desde la relacion, que es donde
    esta declarado el `order_by`: reordenar aqui seria una segunda fuente de
    verdad para el mismo orden.
    """
    return EffectDefinition(
        id=record.id,
        name=record.name,
        type=_effect_type_to_domain(record),
        description=record.description,
        loop=record.loop,
        speed=record.speed,
        fps=record.fps,
        transition_ms=record.transition_ms,
        min_brightness=BRIGHTNESS_MIN if record.min_brightness is None else record.min_brightness,
        max_brightness=BRIGHTNESS_MAX if record.max_brightness is None else record.max_brightness,
        steps=tuple(_step_to_domain(step) for step in record.steps),
        is_builtin=record.is_builtin,
    )


def apply_effect_to_record(record: EffectRecord, effect: EffectDefinition) -> None:
    """Vuelca las columnas escalares de la definicion sobre la fila.

    Los pasos NO se tocan aqui: sustituirlos exige intercalar un `flush` entre
    los DELETE y los INSERT, y eso es semantica de sesion, que pertenece al
    repositorio (ver `step_records`).

    La clave primaria no se toca: `upsert` puede haber resuelto una fila ya
    existente y reescribir el `id` dejaria huerfanos sus `effect_steps`.
    """
    record.name = effect.name
    record.type = effect_type_to_column(effect.type)
    record.description = effect.description
    record.loop = effect.loop
    record.speed = effect.speed
    record.fps = effect.fps
    record.transition_ms = effect.transition_ms
    record.min_brightness = effect.min_brightness
    record.max_brightness = effect.max_brightness
    record.is_builtin = effect.is_builtin
    record.updated_at = utc_now()


def step_records(record: EffectRecord, effect: EffectDefinition) -> list[EffectStepRecord]:
    """Las filas de `effect_steps` que corresponden a esta definicion.

    Se construyen nuevas en vez de conciliar una a una las existentes: los pasos
    son una secuencia posicional sin identidad propia para el usuario -- nadie
    referencia "el paso 2 de Cyberpunk" desde otra tabla -- y conciliar exigiria
    decidir que es "el mismo paso" cuando cambia el color.
    """
    return [
        EffectStepRecord(
            effect_id=record.id,
            position=step.position,
            # to_hex() emite MAYUSCULAS: una sola forma del color en la base.
            color_hex=step.color.to_hex(),
            brightness=step.brightness,
            duration_ms=step.duration_ms,
            easing=None if step.easing is None else step.easing.value,
        )
        for step in effect.steps
    ]


def _effect_type_to_domain(record: EffectRecord) -> EffectType:
    try:
        return EffectType(record.type)
    except ValueError as exc:
        known = ", ".join(sorted(member.value for member in EffectType))
        raise EffectMappingError(
            f"type desconocido en el efecto {record.id}: {record.type!r}."
            f" Valores validos: {known}."
            f" Degradar en silencio ocultaria una fila escrita a mano o por una"
            f" version con mas tipos de efecto que esta."
        ) from exc


def _step_to_domain(record: EffectStepRecord) -> EffectStep:
    try:
        color = RGBColor.from_hex(record.color_hex)
    except ValueError as exc:
        raise EffectMappingError(
            f"color_hex invalido en el paso {record.position} del efecto"
            f" {record.effect_id}: {record.color_hex!r}."
        ) from exc

    return EffectStep(
        position=record.position,
        color=color,
        brightness=record.brightness,
        duration_ms=record.duration_ms,
        easing=_easing_to_domain(record),
    )


def _easing_to_domain(record: EffectStepRecord) -> Easing | None:
    """`NULL` significa "usa el easing por defecto del renderer", no `LINEAR`.

    Es la distincion que permite que un `PULSE` respire con `EASE_IN_OUT` sin
    que nadie tenga que escribirlo en cada paso, y que a la vez un paso pueda
    forzar `LINEAR` de forma explicita.
    """
    if record.easing is None:
        return None
    try:
        return Easing(record.easing)
    except ValueError as exc:
        known = ", ".join(sorted(member.value for member in Easing))
        raise EffectMappingError(
            f"easing desconocido en el paso {record.position} del efecto"
            f" {record.effect_id}: {record.easing!r}. Valores validos: {known}."
        ) from exc
