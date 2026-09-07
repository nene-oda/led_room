"""Algoritmos de render, uno por archivo.

Añadir un quinto renderer no obliga a tocar ninguno de los cuatro existentes:
se crea su archivo y se da de alta en `registry.py`. Esa es la razon concreta
por la que el registro existe (NEXT_STEPS 6.6).
"""

from __future__ import annotations

from backend.app.domain.effects.renderers.base import EffectRenderer
from backend.app.domain.effects.renderers.breath import BreathRenderer
from backend.app.domain.effects.renderers.pulse import PulseRenderer
from backend.app.domain.effects.renderers.smooth_cycle import SmoothCycleRenderer
from backend.app.domain.effects.renderers.static import StaticRenderer

__all__ = [
    "BreathRenderer",
    "EffectRenderer",
    "PulseRenderer",
    "SmoothCycleRenderer",
    "StaticRenderer",
]
