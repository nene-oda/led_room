"""Definicion de un efecto: QUE se quiere que haga la luz, no COMO se pinta.

Separacion deliberada en tres piezas (NEXT_STEPS 6.3):

```text
EffectDefinition  ->  Renderer  ->  Segmentos  ->  LightFrame  ->  LightDevicePort
   (este modulo)     (renderers/)   (segments)      (frames)        (adaptador)
```

Este modulo es **puro**: no conoce SQLModel, ni el reloj, ni el dispositivo. Lo
que se persiste es exactamente esto; lo que se genera en memoria (segmentos y
fotogramas) no se persiste jamas.

`Sunset`, `Cyberpunk`, `Gaming` o `America` **no son tipos**: son filas con
`type = SMOOTH_CYCLE` y paletas distintas. Confundir el catalogo con el
algoritmo es lo que produce el switch gigante que este diseño evita.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.lighting import BRIGHTNESS_MAX, BRIGHTNESS_MIN, Percent, RGBColor

#: Cotas de `speed`. Coinciden con el CHECK `ck_effects_speed`.
SPEED_MIN: Final = 0
SPEED_MAX: Final = 100

#: Velocidad neutra: factor x1. El resto de valores son un multiplicador sobre
#: `transition_ms`, nunca una duracion (ver `engine.speed_factor`).
NEUTRAL_SPEED: Final = 50

#: Cotas de `fps`. Coinciden con el CHECK `ck_effects_fps` y con
#: `Settings.effect_fps`. El tope de 60 es el del esquema, no una promesa: sobre
#: BLE lo sensato son 10-20 (NEXT_STEPS 6.5).
FPS_MIN: Final = 1
FPS_MAX: Final = 60

Speed = Annotated[int, Field(ge=SPEED_MIN, le=SPEED_MAX)]
Fps = Annotated[int, Field(ge=FPS_MIN, le=FPS_MAX)]


class EffectType(StrEnum):
    """Algoritmos de render disponibles (LED_ROOM_DATABASE_MODEL, "Tipos").

    Solo estan los que tienen renderer. `FLASH`, `RANDOM` y `CUSTOM` se dejan
    fuera a proposito: `RANDOM` exige un `random.Random` inyectado para ser
    determinista y `CUSTOM` no es un algoritmo, es un `SMOOTH_CYCLE` con
    `duration_ms` y `easing` por paso (NEXT_STEPS 6.6).
    """

    STATIC = "STATIC"
    SMOOTH_CYCLE = "SMOOTH_CYCLE"
    PULSE = "PULSE"
    BREATH = "BREATH"


class Easing(StrEnum):
    """Curva temporal de una transicion."""

    LINEAR = "LINEAR"
    EASE_IN = "EASE_IN"
    EASE_OUT = "EASE_OUT"
    EASE_IN_OUT = "EASE_IN_OUT"


class ColorSpace(StrEnum):
    """Espacio en el que se interpola el color.

    `HSV` es el valor por defecto y la recomendacion registrada en
    `ARCHITECTURE.md` 8: `#009DFF -> #FF008C` en RGB pasa por `#7F4E7F`, un malva
    sucio y desaturado, mientras que en HSV mantiene S y V al maximo y barre el
    matiz. Se deja como parametro explicito para que la decision sea reversible
    sin tocar ningun renderer.
    """

    HSV = "HSV"
    RGB = "RGB"


class Capability(StrEnum):
    """Capacidades de dispositivo que el motor sabe exigir o degradar.

    El valor de cada miembro es el nombre del campo de `DeviceCapabilities`, y
    hay un test que lo comprueba: sin el, renombrar un campo dejaria la guardia
    de capacidades siempre en verde.

    Solo estan las dos que algun renderer usa hoy. Añadir `addressable` antes de
    que exista un renderer espacial seria infraestructura especulativa.
    """

    RGB = "rgb"
    BRIGHTNESS = "brightness"


class EffectStep(BaseModel):
    """Un vertice del efecto: un color y, opcionalmente, como llegar hasta el.

    Los tres campos opcionales son **anulaciones**: `None` significa "usa lo del
    efecto", no "usa cero". Esa distincion es la que permite que `CUSTOM` sea un
    `SMOOTH_CYCLE` con duracion y easing por paso sin un tipo nuevo.
    """

    model_config = ConfigDict(frozen=True)

    position: int = Field(ge=0)
    color: RGBColor

    brightness: Percent | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    easing: Easing | None = None


class EffectDefinition(BaseModel):
    """Lo que se guarda en `effects` + `effect_steps`, ya en tipos de dominio.

    **Ningun fotograma se persiste**: de aqui salen segmentos y de los segmentos
    fotogramas, siempre en memoria (NEXT_STEPS 6.10).
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str = Field(min_length=1, max_length=120)
    type: EffectType
    description: str | None = None

    loop: bool = False

    #: Multiplicador, no una duracion. La autoridad la tiene `transition_ms`.
    speed: Speed = NEUTRAL_SPEED

    #: Suavidad deseada. El motor aplica ademas el tope de despliegue
    #: (`min(effect.fps, settings.effect_fps)`) al construir el plan.
    fps: Fps = 20

    #: Duracion base de UN segmento, es decir de una transicion entre dos
    #: vertices consecutivos. Con 4000 ms y 20 fps salen 80 fotogramas de 50 ms,
    #: que es el ejemplo del README 12.
    transition_ms: int = Field(default=1000, ge=0)

    #: Envolvente de brillo de `PULSE` y `BREATH`. No se puede expresar con
    #: `effect_steps.brightness`, que es el brillo de UN vertice: la envolvente
    #: necesita dos valores independientes del numero de colores.
    min_brightness: Percent = BRIGHTNESS_MIN
    max_brightness: Percent = BRIGHTNESS_MAX

    #: Tupla y no lista: la definicion es inmutable de arriba a abajo.
    steps: tuple[EffectStep, ...] = ()

    is_builtin: bool = False

    @model_validator(mode="after")
    def _check_invariants(self) -> EffectDefinition:
        if self.min_brightness > self.max_brightness:
            raise ValueError(
                f"min_brightness ({self.min_brightness}) no puede superar a "
                f"max_brightness ({self.max_brightness})."
            )

        positions = [step.position for step in self.steps]
        if len(set(positions)) != len(positions):
            raise ValueError(
                f"Las posiciones de los pasos deben ser unicas; se recibio {positions}."
            )
        if positions != sorted(positions):
            raise ValueError(
                f"Los pasos deben llegar ordenados por posicion; se recibio {positions}."
            )
        return self
