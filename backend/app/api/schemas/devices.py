"""DTOs de dispositivos: registro, lectura y resultados de escaneo."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.domain.devices.models import (
    Device,
    DeviceCapabilities,
    DeviceType,
    DiscoveredDevice,
)


class DeviceCapabilitiesRead(BaseModel):
    """Que sabe hacer el dispositivo. Es lo que decide que renderiza la UI.

    Los campos se enumeran uno a uno en vez de volcar el modelo de dominio: esto
    es el contrato publicado y añadir un campo al dominio no debe cambiarlo por
    accidente (ni al reves).
    """

    rgb: bool
    brightness: bool
    effects: bool
    addressable: bool
    segments: bool
    white_channel: bool
    music_mode: bool

    @classmethod
    def from_domain(cls, capabilities: DeviceCapabilities) -> DeviceCapabilitiesRead:
        return cls(
            rgb=capabilities.rgb,
            brightness=capabilities.brightness,
            effects=capabilities.effects,
            addressable=capabilities.addressable,
            segments=capabilities.segments,
            white_channel=capabilities.white_channel,
            music_mode=capabilities.music_mode,
        )


class DeviceRead(BaseModel):
    """Un dispositivo registrado, con su estado de enlace.

    `connected` NO viene del dominio `Device` (que solo modela identidad
    persistida) sino del estado global: se compone aqui, en la frontera, porque
    es justo lo que un cliente necesita ver junto.
    """

    #: Cadena, no UUID: el JSON no tiene tipo UUID y el frontend no debe
    #: inventarse la conversion.
    id: str
    name: str
    adapter_type: DeviceType
    address: str | None = None
    enabled: bool
    auto_connect: bool
    connected: bool
    capabilities: DeviceCapabilitiesRead

    @classmethod
    def from_domain(cls, device: Device, *, connected: bool) -> DeviceRead:
        return cls(
            id=str(device.id),
            name=device.name,
            adapter_type=device.adapter_type,
            address=device.address,
            enabled=device.enabled,
            auto_connect=device.auto_connect,
            connected=connected,
            capabilities=DeviceCapabilitiesRead.from_domain(device.capabilities),
        )


class DiscoveredDeviceRead(BaseModel):
    """Resultado de `GET /devices/scan` (README 16).

    Sin `id` a proposito: lo descubierto todavia no existe en la base. Lo que le
    da identidad es `POST /devices`.
    """

    name: str | None = None
    address: str
    rssi: int | None = None

    @classmethod
    def from_domain(cls, discovered: DiscoveredDevice) -> DiscoveredDeviceRead:
        return cls(name=discovered.name, address=discovered.address, rssi=discovered.rssi)


class DeviceCreateRequest(BaseModel):
    """Cuerpo de `POST /devices`.

    Este endpoint no esta en el README y hace falta: `/devices/{id}/connect`
    presupone un id persistido y `/devices/scan` devuelve resultados efimeros
    sin id. Registrar lo descubierto es lo que evita escribir una direccion a
    mano en el codigo (NEXT_STEPS 4.3).

    `adapter_type` es opcional porque el proceso construye UN adaptador
    (`LED_ROOM_DEVICE_ADAPTER`) y el escaneo que produjo la direccion lo hizo el
    descubridor de esa misma familia. Se acepta para que el cliente pueda
    afirmar lo que cree estar registrando, y se rechaza con 422 si contradice a
    la configuracion: aceptarlo y guardar otra cosa seria etiquetar mal el
    dispositivo en silencio.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=255)
    adapter_type: DeviceType | None = None

    def to_domain(self) -> DiscoveredDevice:
        """Lo convierte en la entrada que espera el caso de uso de registro."""
        return DiscoveredDevice(name=self.name, address=self.address)
