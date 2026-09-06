"""Tipos de iluminacion compartidos por el dominio.

Modulo hoja, sin dependencias de otros paquetes del proyecto: tanto el puerto de
dispositivos como el futuro motor de efectos necesitan estos tipos, y ubicarlos
aqui evita que `devices` acabe importando `effects`.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")

#: Brillo minimo y maximo. El dominio y la API trabajan SIEMPRE en porcentaje;
#: la escala del hardware es asunto exclusivo del adaptador. Ver design.md D3.
BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 100


class RGBColor(BaseModel):
    """Color RGB con canales 0-255 (README 8)."""

    model_config = ConfigDict(frozen=True)

    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)

    @classmethod
    def from_hex(cls, value: str) -> RGBColor:
        """Construye el color desde `#RRGGBB` (con o sin almohadilla)."""
        match = _HEX_RE.match(value.strip())
        if match is None:
            raise ValueError(f"Color hexadecimal invalido: {value!r}; se esperaba #RRGGBB")
        digits = match.group(1)
        return cls(
            r=int(digits[0:2], 16),
            g=int(digits[2:4], 16),
            b=int(digits[4:6], 16),
        )

    def to_hex(self) -> str:
        """Representacion canonica `#RRGGBB` en mayusculas."""
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"


class LightFrame(BaseModel):
    """Unidad de salida del motor de efectos (README 11).

    El motor generara secuencias de estos fotogramas y los entregara al
    `LightDevicePort`. El cliente nunca los genera.
    """

    model_config = ConfigDict(frozen=True)

    color: RGBColor
    brightness: int = Field(ge=BRIGHTNESS_MIN, le=BRIGHTNESS_MAX)
    duration_ms: int = Field(gt=0)
