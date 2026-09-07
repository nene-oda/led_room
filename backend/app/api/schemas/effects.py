"""DTOs de efectos: cuerpos de escritura y lectura del catalogo.

Dos decisiones del contrato que no son evidentes:

* **El color de un paso viaja como `#RRGGBB`**, no como `{r,g,b}`. Es la forma
  canonica de las *listas de colores* (ARCHITECTURE 3.2); `{r,g,b}` es la de las
  mutaciones puntuales de luz. Se acepta en minusculas al escribir -- un cliente
  no deberia fallar por eso -- y se devuelve siempre en MAYUSCULAS.
* **La posicion de un paso es su indice en el array**, y no un campo. Asi dos
  pasos con la misma posicion son irrepresentables, en vez de ser un 422 que
  haya que redactar.

`is_builtin` no se acepta al escribir: lo decide el servidor, y aceptarlo
dejaria que un cliente marcara como "de fabrica" un efecto que creo el.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.api.schemas.lights import HEX_COLOR_PATTERN
from backend.app.domain.effects.models import (
    FPS_MAX,
    FPS_MIN,
    NEUTRAL_SPEED,
    SPEED_MAX,
    SPEED_MIN,
    Easing,
    EffectDefinition,
    EffectStep,
    EffectType,
)
from backend.app.domain.lighting import BRIGHTNESS_MAX, BRIGHTNESS_MIN, Percent, RGBColor

#: Al ESCRIBIR se aceptan las dos cajas: exigir mayusculas convertiria un
#: `#7b00ff` copiado de cualquier selector de color en un 422 inutil.
WRITABLE_HEX_PATTERN = r"^#[0-9a-fA-F]{6}$"


class EffectStepWrite(BaseModel):
    """Un vertice del efecto. Los tres opcionales son **anulaciones**."""

    color: str = Field(pattern=WRITABLE_HEX_PATTERN, examples=["#009DFF"])

    #: `None` = usa el brillo base del efecto. No es lo mismo que 0.
    brightness: Percent | None = None

    #: `None` = usa `transition_ms` del efecto. Es lo que hace que `CUSTOM` sea
    #: un `SMOOTH_CYCLE` con duracion por paso y no un tipo nuevo.
    duration_ms: int | None = Field(default=None, ge=0)

    #: `None` = usa la curva por defecto del algoritmo (`EASE_IN_OUT` en
    #: `PULSE`, `LINEAR` en `SMOOTH_CYCLE`).
    easing: Easing | None = None

    def to_domain(self, position: int) -> EffectStep:
        return EffectStep(
            position=position,
            color=RGBColor.from_hex(self.color),
            brightness=self.brightness,
            duration_ms=self.duration_ms,
            easing=self.easing,
        )


class EffectWrite(BaseModel):
    """Cuerpo de `POST /effects` y de `PUT /effects/{id}`.

    Los rangos se repiten aunque `EffectDefinition` ya los valide, por el mismo
    motivo que en `ColorRequest`: este modelo protege el contrato **publicado** y
    lo documenta en el OpenAPI; el de dominio protege la invariante del modelo.
    """

    name: str = Field(min_length=1, max_length=120)
    type: EffectType
    description: str | None = None

    loop: bool = False

    #: Multiplicador de la duracion, no una duracion:
    #: `factor = 2 ** ((50 - speed) / 50)`. 0 = mitad de velocidad, 100 = doble.
    speed: int = Field(default=NEUTRAL_SPEED, ge=SPEED_MIN, le=SPEED_MAX)

    #: Suavidad deseada. El servidor aplica ademas su propio tope
    #: (`LED_ROOM_EFFECT_FPS`): pedir 60 no inunda el enlace BLE.
    fps: int = Field(default=20, ge=FPS_MIN, le=FPS_MAX)

    #: Duracion base de UNA transicion entre dos vertices consecutivos.
    transition_ms: int = Field(default=1000, ge=0)

    #: Envolvente de brillo de `PULSE` y `BREATH`; los demas tipos usan
    #: `max_brightness` como brillo base de un paso sin brillo propio.
    min_brightness: Percent = BRIGHTNESS_MIN
    max_brightness: Percent = BRIGHTNESS_MAX

    steps: list[EffectStepWrite] = Field(default_factory=list)

    def to_domain(self, effect_id: UUID) -> EffectDefinition:
        """Construye la definicion de dominio, que es quien valida de verdad.

        El numero de pasos NO se valida aqui: cuantos admite cada algoritmo lo
        declara su renderer, y repetirlo en el DTO seria una segunda copia de la
        regla que acabaria divergiendo.
        """
        return EffectDefinition(
            id=effect_id,
            name=self.name,
            type=self.type,
            description=self.description,
            loop=self.loop,
            speed=self.speed,
            fps=self.fps,
            transition_ms=self.transition_ms,
            min_brightness=self.min_brightness,
            max_brightness=self.max_brightness,
            steps=tuple(step.to_domain(position) for position, step in enumerate(self.steps)),
        )


class EffectStepRead(BaseModel):
    position: int = Field(ge=0)
    color: str = Field(pattern=HEX_COLOR_PATTERN, examples=["#009DFF"])
    brightness: Percent | None = None
    duration_ms: int | None = None
    easing: Easing | None = None

    @classmethod
    def from_domain(cls, step: EffectStep) -> EffectStepRead:
        return cls(
            position=step.position,
            # to_hex() emite MAYUSCULAS, que es lo que exige el contrato.
            color=step.color.to_hex(),
            brightness=step.brightness,
            duration_ms=step.duration_ms,
            easing=step.easing,
        )


class EffectRead(BaseModel):
    """Un efecto tal y como se publica."""

    id: str
    name: str
    type: EffectType
    description: str | None = None
    loop: bool
    speed: int
    fps: int
    transition_ms: int
    min_brightness: Percent
    max_brightness: Percent
    is_builtin: bool
    steps: list[EffectStepRead]

    @classmethod
    def from_domain(cls, effect: EffectDefinition) -> EffectRead:
        return cls(
            id=str(effect.id),
            name=effect.name,
            type=effect.type,
            description=effect.description,
            loop=effect.loop,
            speed=effect.speed,
            fps=effect.fps,
            transition_ms=effect.transition_ms,
            min_brightness=effect.min_brightness,
            max_brightness=effect.max_brightness,
            is_builtin=effect.is_builtin,
            steps=[EffectStepRead.from_domain(step) for step in effect.steps],
        )
