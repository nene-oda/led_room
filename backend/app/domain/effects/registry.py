"""Tabla `EffectType` -> renderer. Punto unico de extension del motor.

Existe por un motivo concreto y no por simetria: es lo que permite que añadir un
efecto sea **un archivo y una entrada**, sin tocar los renderers existentes ni
el bucle de reproduccion (NEXT_STEPS 6.6). Un test recorre `EffectType` y falla
si algun miembro se queda sin renderer.

En la Fase 11 (hardware direccionable) este mismo registro se indexara por
`(EffectType, addressable)`: la misma definicion producira una secuencia temporal
o un gradiente espacial sin cambiar `LightDevicePort` ni la API.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from backend.app.domain.effects.models import EffectType
from backend.app.domain.effects.renderers import (
    BreathRenderer,
    EffectRenderer,
    PulseRenderer,
    SmoothCycleRenderer,
    StaticRenderer,
)

#: Los renderers no tienen estado, asi que se comparte una instancia. Cualquier
#: estado por reproduccion vive en el `EffectPlan`, que es de un solo uso.
RENDERERS: Final[Mapping[EffectType, EffectRenderer]] = {
    EffectType.STATIC: StaticRenderer(),
    EffectType.SMOOTH_CYCLE: SmoothCycleRenderer(),
    EffectType.PULSE: PulseRenderer(),
    EffectType.BREATH: BreathRenderer(),
}


def renderer_for(effect_type: EffectType) -> EffectRenderer:
    """Renderer del tipo pedido.

    Un `KeyError` aqui seria un miembro nuevo de `EffectType` sin dar de alta, y
    el test de cobertura del registro lo detecta antes de que llegue a ejecucion.
    """
    return RENDERERS[effect_type]
