"""Configuracion de la aplicacion (variables de entorno LED_ROOM_*)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_core import ErrorDetails
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.domain.devices.models import DeviceType

# backend/app/config.py -> backend/app -> backend -> raiz del repositorio
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _is_blank(value: object) -> bool:
    return isinstance(value, str) and not value.strip()


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
    # "null" por defecto para que el servicio arranque en cualquier host, tenga
    # o no radio Bluetooth.
    #
    # Es el enum del DOMINIO, no un Literal propio: antes habia tres
    # vocabularios para el mismo concepto (este Literal, `DeviceType` y el
    # documento de BD) y nada obligaba a que coincidieran (NEXT_STEPS A1).
    device_adapter: DeviceType = DeviceType.NULL

    # Familia que DESCUBRE, cuando no es la misma que controla.
    #
    # Existe porque descubrir y controlar son dos puertos distintos
    # (`DeviceDiscoveryPort` y `LightDevicePort`) y hoy estan en fases
    # distintas: el escaner BLE ya es real, mientras que el adaptador
    # LotusLantern no puede escribir nada hasta que la Fase 0 verifique el
    # protocolo. `AdapterRegistration` ya los tenia separados; lo que los
    # acoplaba era esta configuracion, con una sola palanca para los dos.
    #
    # `None` = "la misma que controla", que es lo correcto en cuanto exista el
    # adaptador BLE. Mientras tanto, `LED_ROOM_DEVICE_ADAPTER=null` +
    # `LED_ROOM_DEVICE_DISCOVERY=lotus_lantern` da busqueda BLE real en un
    # servicio que arranca en cualquier host.
    device_discovery: DeviceType | None = None

    ble_scan_timeout: float = Field(default=10.0, gt=0, le=120)

    # Restringir el escaneo a los anuncios cuyo nombre contenga
    # `LED_ROOM_DEVICE_NAME`. **Desactivado a proposito**: un controlador de esta
    # clase puede anunciarse como ELK-BLEDOM, ELK-BLEDOB, MELK-..., LEDBLE-... o
    # sin nombre, asi que filtrar de serie esconderia justo lo que se busca.
    # Se enciende cuando ya se sabe como se llama y el vecindario estorba.
    ble_scan_name_filter: bool = False

    # Un connect() BLE que no responde y un write_gatt_char colgado bloquean el
    # unico escritor del dispositivo y congelan la aplicacion entera. Los dos
    # timeouts son la red de seguridad de `BleConnection` (NEXT_STEPS 4.2).
    ble_connect_timeout: float = Field(default=20.0, gt=0, le=120)
    ble_write_timeout: float = Field(default=5.0, gt=0, le=60)

    # Cota de escrituras al dispositivo por segundo (throttling de ultimo valor
    # gana, README 18). DELIBERADAMENTE separado de `effect_fps`: uno protege el
    # enlace BLE y el otro define la suavidad de un efecto. Acoplarlos hace que
    # subir los fps de un efecto inunde el BLE.
    ble_max_updates_per_second: int = Field(default=20, ge=1, le=60)

    # 20 fps es el valor del README 11. La cota superior evita que un valor
    # absurdo sature el enlace BLE.
    effect_fps: int = Field(default=20, ge=1, le=60)

    log_level: LogLevel = "INFO"

    @model_validator(mode="before")
    @classmethod
    def _blank_env_means_unset(cls, data: object) -> object:
        """Una variable de entorno vacia equivale a no haberla definido.

        Docker Compose no omite `LED_ROOM_DEVICE_DISCOVERY: ${LED_ROOM_DEVICE_DISCOVERY:-}`
        cuando la variable no existe en el host: la inyecta con cadena vacia.
        Lo mismo hacen muchos CI y un `.env` con `LED_ROOM_X=`. Pydantic veia
        entonces `''`, que no es miembro de `DeviceType` ni `None`, y el
        contenedor moria al arrancar.

        Se descartan solo las cadenas en blanco, antes de validar, para que el
        campo caiga en su valor por defecto. Un valor equivocado pero presente
        (`LED_ROOM_DEVICE_DISCOVERY=lotus_lanturn`) sigue fallando: esto no
        tolera configuracion invalida, solo reconoce la ausencia.
        """
        if not isinstance(data, dict):
            return data
        return {key: value for key, value in data.items() if not _is_blank(value)}

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @property
    def discovery_adapter(self) -> DeviceType:
        """Familia cuyo `DeviceDiscoveryPort` se usa; por defecto, la que controla."""
        return self.device_discovery or self.device_adapter

    @property
    def scan_name_filter(self) -> str | None:
        """Texto que debe contener el nombre anunciado, o `None` si no se filtra."""
        return self.device_name if self.ble_scan_name_filter else None

    @property
    def frontend_available(self) -> bool:
        """True si hay un SPA compilado que servir."""
        return (self.frontend / "index.html").is_file()

    @property
    def frame_duration_ms(self) -> int:
        """Duracion de un fotograma derivada de los fps configurados (README 12)."""
        return round(1000 / self.effect_fps)

    @property
    def throttle_interval_ms(self) -> int:
        """Intervalo minimo entre escrituras al dispositivo (README 18)."""
        return round(1000 / self.ble_max_updates_per_second)


class ConfigurationError(RuntimeError):
    """Una variable `LED_ROOM_*` tiene un valor que la aplicacion no acepta.

    Traduce el error de Pydantic al vocabulario del operador: el nombre de la
    variable de entorno en lugar del nombre del campo, y el valor recibido.
    Quien la reciba debe parar; arrancar con configuracion invalida no es un
    modo degradado valido.
    """


def _describe(error: ErrorDetails) -> str:
    location = error["loc"]
    field = str(location[0]) if location else "?"
    variable = f"{Settings.model_config['env_prefix']}{field.upper()}"
    return f"  {variable}={error['input']!r}: {error['msg']}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ajustes del proceso; falla con un mensaje accionable si son invalidos.

    La traza de `pydantic_settings` nombra el campo (`device_discovery`), no la
    variable que el operador escribio (`LED_ROOM_DEVICE_DISCOVERY`), y en un
    contenedor ese log es la unica pista disponible.
    """
    try:
        return Settings()
    except ValidationError as error:
        detail = "\n".join(_describe(item) for item in error.errors())
        raise ConfigurationError(f"Configuracion invalida:\n{detail}") from None
