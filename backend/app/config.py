"""Configuracion de la aplicacion (variables de entorno LED_ROOM_*)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> raiz del repositorio
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DeviceAdapter = Literal["null", "lotus_lantern"]


class Settings(BaseSettings):
    """Ajustes leidos del entorno o de .env con prefijo LED_ROOM_ (README 26)."""

    model_config = SettingsConfigDict(
        env_prefix="LED_ROOM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)

    # En Windows /data no existe: por defecto usamos <repo>/data/led-room.db.
    # En el contenedor se sobreescribe con LED_ROOM_DATABASE=/data/led-room.db.
    database: Path = REPO_ROOT / "data" / "led-room.db"

    # Salida de `npm run build`. En el contenedor: LED_ROOM_FRONTEND=/app/frontend.
    frontend: Path = REPO_ROOT / "frontend" / "dist"

    device_name: str = "ELK-BLEDOM"

    # Selecciona la implementacion de LightDevicePort sin acoplar el dominio.
    # "null" por defecto para que el servicio arranque en cualquier host,
    # tenga o no radio Bluetooth. Ver design.md D10.
    device_adapter: DeviceAdapter = "null"

    ble_scan_timeout: float = Field(default=10.0, gt=0, le=120)

    # 20 fps es el valor del README 11. La cota superior evita que un valor
    # absurdo sature el enlace BLE.
    effect_fps: int = Field(default=20, ge=1, le=60)

    log_level: LogLevel = "INFO"

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @property
    def frontend_available(self) -> bool:
        """True si hay un SPA compilado que servir."""
        return (self.frontend / "index.html").is_file()

    @property
    def frame_duration_ms(self) -> int:
        """Duracion de un fotograma derivada de los fps configurados (README 12)."""
        return round(1000 / self.effect_fps)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
