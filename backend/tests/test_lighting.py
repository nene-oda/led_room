from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.domain.lighting import LightFrame, RGBColor


@pytest.mark.parametrize(
    ("hex_value", "expected"),
    [
        ("#7B00FF", (123, 0, 255)),
        ("7B00FF", (123, 0, 255)),
        ("#003cff", (0, 60, 255)),
        ("#000000", (0, 0, 0)),
        ("#FFFFFF", (255, 255, 255)),
    ],
)
def test_from_hex(hex_value: str, expected: tuple[int, int, int]) -> None:
    color = RGBColor.from_hex(hex_value)

    assert (color.r, color.g, color.b) == expected


@pytest.mark.parametrize("hex_value", ["#7B00F", "#GGGGGG", "", "0x7B00FF", "#7B00FF00"])
def test_from_hex_rechaza_valores_invalidos(hex_value: str) -> None:
    with pytest.raises(ValueError):
        RGBColor.from_hex(hex_value)


def test_ida_y_vuelta_hexadecimal() -> None:
    assert RGBColor.from_hex("#8214FF").to_hex() == "#8214FF"


def test_to_hex_usa_mayusculas() -> None:
    assert RGBColor(r=0, g=60, b=255).to_hex() == "#003CFF"


@pytest.mark.parametrize("channel", ["r", "g", "b"])
@pytest.mark.parametrize("value", [-1, 256])
def test_canal_fuera_de_rango_se_rechaza(channel: str, value: int) -> None:
    kwargs = {"r": 0, "g": 0, "b": 0, channel: value}

    with pytest.raises(ValidationError):
        RGBColor(**kwargs)


def test_light_frame_valido() -> None:
    frame = LightFrame(color=RGBColor.from_hex("#7B22FF"), brightness=65, duration_ms=50)

    assert frame.brightness == 65
    assert frame.duration_ms == 50


@pytest.mark.parametrize("brightness", [-1, 101])
def test_light_frame_rechaza_brillo_fuera_de_porcentaje(brightness: int) -> None:
    with pytest.raises(ValidationError):
        LightFrame(color=RGBColor(r=0, g=0, b=0), brightness=brightness, duration_ms=50)


@pytest.mark.parametrize("duration_ms", [0, -50])
def test_light_frame_rechaza_duracion_no_positiva(duration_ms: int) -> None:
    with pytest.raises(ValidationError):
        LightFrame(color=RGBColor(r=0, g=0, b=0), brightness=50, duration_ms=duration_ms)
