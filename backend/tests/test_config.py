from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_valores_por_defecto() -> None:
    settings = Settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.device_name == "ELK-BLEDOM"
    assert settings.device_adapter == "null"
    assert settings.ble_scan_timeout == 10.0
    assert settings.effect_fps == 20
    assert settings.log_level == "INFO"


def test_variable_de_entorno_respetada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LED_ROOM_PORT", "9000")

    assert Settings().port == 9000


def test_puerto_no_numerico_falla_con_error_de_validacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LED_ROOM_PORT", "no-es-un-puerto")

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "port" in str(excinfo.value)


@pytest.mark.parametrize("fps", ["0", "61"])
def test_fps_fuera_de_rango_falla(monkeypatch: pytest.MonkeyPatch, fps: str) -> None:
    monkeypatch.setenv("LED_ROOM_EFFECT_FPS", fps)

    with pytest.raises(ValidationError):
        Settings()


def test_nivel_de_log_se_normaliza(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LED_ROOM_LOG_LEVEL", "debug")

    assert Settings().log_level == "DEBUG"


def test_duracion_de_fotograma_derivada_de_los_fps() -> None:
    """README 12: transition 4000 ms a 20 fps -> 80 fotogramas de 50 ms."""
    assert Settings().frame_duration_ms == 50
