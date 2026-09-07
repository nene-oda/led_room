"""Tablas `devices`, `device_capabilities` y `device_state`.

LED_ROOM_DATABASE_MODEL 5-7 y 39-41.

Ojo con dos cosas que este modulo hace a proposito y no deben "arreglarse":

* NO usa `from __future__ import annotations`. Con las anotaciones diferidas,
  SQLModel 0.0.42 le pasa a SQLAlchemy la cadena entera `"X | None"` como
  nombre de clase destino de la relacion y el mapeo revienta con
  `failed to locate a name ('DeviceCapabilitiesRecord | None')`. Verificado.
* Por eso las relaciones opcionales se anotan `Optional["X"]` y no `X | None`.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, Relationship, SQLModel

from backend.app.infrastructure.persistence.models.base import UtcDateTime, utc_now

if TYPE_CHECKING:  # pragma: no cover - solo para el verificador de tipos
    from backend.app.infrastructure.persistence.models.effect import EffectRecord
    from backend.app.infrastructure.persistence.models.scene import SceneRecord, SceneTargetRecord


class DeviceRecord(SQLModel, table=True):
    """Un controlador fisico conocido por el sistema."""

    __tablename__ = "devices"

    __table_args__ = (
        # El mismo controlador fisico no puede registrarse dos veces: dos
        # escaneos devuelven la misma direccion y `POST /devices` crearia un
        # duplicado que dejaria ambiguo `get_by_address`. Es un INDICE unico y
        # no un UniqueConstraint a proposito: `CREATE UNIQUE INDEX` es nativo en
        # SQLite y evita la recreacion de tabla del modo batch, arriesgada aqui
        # porque `device_capabilities`, `device_state` y `scene_targets` apuntan
        # a esta tabla con las claves foraneas ACTIVADAS.
        # En SQLite los NULL son distintos entre si, asi que varios dispositivos
        # sin direccion (el adaptador nulo) siguen conviviendo.
        Index("uq_devices_adapter_type_ble_address", "adapter_type", "ble_address", unique=True),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    name: str = Field(max_length=120, index=True)

    #: Selecciona la implementacion de `LightDevicePort`. Es SOLO un
    #: identificador de tipo de adaptador: aqui no se guardan UUID de servicio,
    #: bytes de comando ni nada del protocolo BLE, que sigue sin verificar.
    adapter_type: str = Field(max_length=50, index=True)

    ble_name: Optional[str] = Field(default=None, max_length=120, index=True)  # noqa: UP045

    #: Identidad BLE descubierta por escaneo, nunca escrita a mano en el codigo.
    #: En Windows es un GUID de WinRT y en Linux una MAC: por eso es texto libre.
    ble_address: Optional[str] = Field(default=None, max_length=255, index=True)  # noqa: UP045

    enabled: bool = Field(default=True)
    auto_connect: bool = Field(default=True)

    created_at: datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)
    updated_at: datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)

    capabilities: Optional["DeviceCapabilitiesRecord"] = Relationship(
        back_populates="device",
        # 1:1 de verdad y borrado en cascada tambien en la sesion de Python, no
        # solo en el motor: sin esto, borrar un DeviceRecord por ORM deja huerfana la
        # fila hija que ya estuviera cargada en memoria.
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )

    state: Optional["DeviceStateRecord"] = Relationship(
        back_populates="device",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )

    scene_targets: list["SceneTargetRecord"] = Relationship(
        back_populates="device",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class DeviceCapabilitiesRecord(SQLModel, table=True):
    """Que sabe hacer el hardware. Es lo que mantiene el modelo agnostico."""

    __tablename__ = "device_capabilities"

    device_id: UUID = Field(foreign_key="devices.id", ondelete="CASCADE", primary_key=True)

    supports_rgb: bool = Field(default=True)
    supports_brightness: bool = Field(default=True)
    supports_effects: bool = Field(default=False)

    addressable: bool = Field(default=False)
    supports_segments: bool = Field(default=False)
    white_channel: bool = Field(default=False)
    music_mode: bool = Field(default=False)

    device: "DeviceRecord" = Relationship(back_populates="capabilities")


class DeviceStateRecord(SQLModel, table=True):
    """Ultimo estado DESEADO. No es el estado fisico instantaneo.

    El estado efimero (conectado, RSSI, fotograma actual) vive en memoria
    (LED_ROOM_DATABASE_MODEL 29).
    """

    __tablename__ = "device_state"

    __table_args__ = (
        CheckConstraint(
            "brightness >= 0 AND brightness <= 100",
            name="ck_device_state_brightness",
        ),
        # ARCHITECTURE 3.2 exige #RRGGBB en MAYUSCULAS. GLOB distingue
        # mayusculas de minusculas en SQLite; LIKE no lo haria.
        CheckConstraint(
            "color_hex GLOB '#[0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F]'",
            name="ck_device_state_color_hex",
        ),
    )

    device_id: UUID = Field(foreign_key="devices.id", ondelete="CASCADE", primary_key=True)

    power: bool = Field(default=False)

    color_hex: str = Field(default="#FFFFFF", max_length=7)

    #: Porcentaje 0-100 SIEMPRE (ARCHITECTURE 3.3). La escala del hardware
    #: (0-255 tipicamente) se convierte dentro del adaptador, jamas aqui.
    brightness: int = Field(default=100, ge=0, le=100)

    active_scene_id: Optional[UUID] = Field(  # noqa: UP045
        default=None,
        foreign_key="scenes.id",
        ondelete="SET NULL",
    )

    active_effect_id: Optional[UUID] = Field(  # noqa: UP045
        default=None,
        foreign_key="effects.id",
        ondelete="SET NULL",
    )

    updated_at: datetime = Field(default_factory=utc_now, sa_type=UtcDateTime)

    device: "DeviceRecord" = Relationship(back_populates="state")
    active_scene: Optional["SceneRecord"] = Relationship()
    active_effect: Optional["EffectRecord"] = Relationship()
