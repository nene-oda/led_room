"""Degradacion de un fotograma segun lo que el dispositivo sabe hacer.

Es el **borde de renderizado**, el ultimo paso antes de `apply_frame`
(NEXT_STEPS 6.8):

* **Requisito duro no cumplido** -> se rechaza al construir el `EffectPlan`, con
  cero escrituras. Eso ocurre en `engine.build_plan`, no aqui.
* **Requisito blando** -> se degrada aqui. Si el dispositivo no controla el
  brillo, el brillo se pliega multiplicativamente sobre el color.

**La definicion persistida no cambia nunca.** La adaptacion se calcula por
fotograma y se tira: guardar un efecto ya degradado lo ataria al hardware que
habia conectado el dia que se guardo.
"""

from __future__ import annotations

from backend.app.domain.devices.models import DeviceCapabilities
from backend.app.domain.effects.models import Capability
from backend.app.domain.lighting import BRIGHTNESS_MAX, LightFrame, RGBColor


def supports(capabilities: DeviceCapabilities, capability: Capability) -> bool:
    """Consulta una capacidad por su nombre de dominio.

    El valor de cada miembro de `Capability` es el nombre del campo de
    `DeviceCapabilities`; un test comprueba que sigan coincidiendo, porque un
    `getattr` sobre un nombre obsoleto reventaria en caliente, a mitad de efecto.
    """
    return bool(getattr(capabilities, capability.value))


def missing_capabilities(
    required: frozenset[Capability],
    capabilities: DeviceCapabilities,
) -> frozenset[Capability]:
    """Requisitos duros que este dispositivo no cumple. Vacio = se puede pintar."""
    return frozenset(
        capability for capability in required if not supports(capabilities, capability)
    )


def adapt_frame(frame: LightFrame, capabilities: DeviceCapabilities) -> LightFrame:
    """Ajusta un fotograma a lo que el dispositivo acepta.

    Hoy solo hay una degradacion: sin control de brillo, el brillo se pliega
    sobre el color y el fotograma sale al maximo, que para ese hardware es el
    unico valor con sentido.
    """
    if supports(capabilities, Capability.BRIGHTNESS):
        return frame

    return LightFrame(
        color=scale(frame.color, frame.brightness),
        brightness=BRIGHTNESS_MAX,
        duration_ms=frame.duration_ms,
    )


def scale(color: RGBColor, brightness: int) -> RGBColor:
    """Atenua un color por un porcentaje 0-100.

    Es una aproximacion lineal deliberada: la gamma real del driver PWM del
    controlador es desconocida (Fase 0), asi que cualquier correccion seria un
    numero inventado.
    """
    factor = brightness / BRIGHTNESS_MAX
    return RGBColor(
        r=round(color.r * factor),
        g=round(color.g * factor),
        b=round(color.b * factor),
    )
