"""DTOs de la luz: cuerpos de mutacion y lectura del estado deseado."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.domain.lighting import LightState, Percent, RGBColor

#: Forma canonica del color en las LECTURAS (ARCHITECTURE 3.2). Se declara en el
#: esquema para que aparezca en el OpenAPI y llegue a los tipos generados del
#: frontend (NEXT_STEPS A7): un cliente no deberia tener que descubrir a mano
#: que el hexadecimal va en mayusculas.
HEX_COLOR_PATTERN = r"^#[0-9A-F]{6}$"


class PowerRequest(BaseModel):
    """Cuerpo de `POST /lights/power` y del comando `light.power`."""

    on: bool


class ColorRequest(BaseModel):
    """Cuerpo de `PUT /lights/color` y del comando `light.color`.

    Los rangos se repiten aqui aunque `RGBColor` ya los valide, porque protegen
    cosas distintas: este modelo protege el **contrato publicado** (y lo
    documenta en el OpenAPI), y el de dominio protege la invariante del modelo.
    Sin ellos, un 300 se rechazaria igual, pero el esquema publicado no diria
    cual es el rango valido.
    """

    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)

    def to_domain(self) -> RGBColor:
        return RGBColor(r=self.r, g=self.g, b=self.b)


class BrightnessRequest(BaseModel):
    """Cuerpo de `PUT /lights/brightness` y del comando `light.brightness`."""

    #: `Percent` es la UNICA definicion del 0-100 del proyecto; repetir aqui un
    #: `Field(ge=0, le=100)` seria la forma de que algun dia acepte 101.
    brightness: Percent


class LightStateRead(BaseModel):
    """Estado deseado de la luz tal y como se publica.

    El color sale como `#RRGGBB` y no como `{r,g,b}`: es una lectura, y la
    representacion de lectura del proyecto es la cadena hexadecimal.
    """

    power: bool
    color: str = Field(pattern=HEX_COLOR_PATTERN, examples=["#7B00FF"])
    brightness: Percent

    @classmethod
    def from_domain(cls, state: LightState) -> LightStateRead:
        return cls(
            power=state.power,
            # to_hex() emite MAYUSCULAS, que es lo que exige el contrato.
            color=state.color.to_hex(),
            brightness=state.brightness,
        )
