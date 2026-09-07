from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain.devices.models import (
    SINGLE_COLOR_STRIP,
    Device,
    DeviceStatus,
    DeviceType,
    DiscoveredDevice,
)
from backend.app.domain.devices.ports import DeviceDiscoveryPort
from backend.app.domain.devices.repositories import DeviceRepository
from backend.app.domain.lighting import LightState, RGBColor

ADDRESS = "AA:BB:CC:DD:EE:FF"


def _device(
    *,
    device_id: UUID | None = None,
    address: str | None = ADDRESS,
    enabled: bool = True,
) -> Device:
    return Device(
        id=device_id if device_id is not None else uuid4(),
        name="Tira del salon",
        adapter_type=DeviceType.LOTUS_LANTERN,
        address=address,
        enabled=enabled,
        capabilities=SINGLE_COLOR_STRIP,
    )


def _assign(target: object, attribute: str, value: object) -> None:
    """Asignacion indirecta: probar la inmutabilidad sin discutir con el verificador."""
    setattr(target, attribute, value)


def test_el_dispositivo_se_identifica_con_un_uuid() -> None:
    device_id = uuid4()

    assert _device(device_id=device_id).id == device_id


def test_el_dispositivo_acepta_el_uuid_como_cadena() -> None:
    """El DTO de la API lo entregara como texto; el dominio sigue siendo UUID."""
    device = Device.model_validate(
        {
            "id": "0f7a4d3e-3b0e-4a1e-9c9f-2a6f3d5f7c11",
            "name": "Tira del salon",
            "adapter_type": "lotus_lantern",
            "address": ADDRESS,
            "capabilities": SINGLE_COLOR_STRIP.model_dump(),
        }
    )

    assert device.id == UUID("0f7a4d3e-3b0e-4a1e-9c9f-2a6f3d5f7c11")
    assert device.adapter_type is DeviceType.LOTUS_LANTERN


def test_el_dispositivo_no_guarda_si_esta_conectado() -> None:
    """La identidad persistida no mezcla estado efimero (NEXT_STEPS A1)."""
    assert "connected" not in Device.model_fields


def test_valores_por_defecto_del_dispositivo() -> None:
    device = _device()

    assert device.enabled
    assert device.auto_connect


def test_la_direccion_puede_faltar_hasta_que_haya_un_escaneo() -> None:
    assert _device(address=None).address is None


def test_el_dispositivo_es_inmutable() -> None:
    device = _device()

    with pytest.raises(ValidationError):
        _assign(device, "name", "otro")


def test_el_tipo_de_adaptador_es_el_vocabulario_unico() -> None:
    """Un valor inventado se rechaza: no hay una segunda lista de adaptadores."""
    with pytest.raises(ValidationError):
        Device.model_validate(
            {
                "id": uuid4(),
                "name": "Tira",
                "adapter_type": "wled",
                "capabilities": SINGLE_COLOR_STRIP.model_dump(),
            }
        )


def test_las_capacidades_incluyen_el_modo_musica() -> None:
    """La columna `music_mode` existe en la base; sin esto el mapper seria parcial."""
    assert "music_mode" in SINGLE_COLOR_STRIP.model_dump()
    assert not SINGLE_COLOR_STRIP.music_mode


def test_el_hardware_actual_no_es_direccionable() -> None:
    assert SINGLE_COLOR_STRIP.rgb
    assert SINGLE_COLOR_STRIP.brightness
    assert not SINGLE_COLOR_STRIP.addressable
    assert not SINGLE_COLOR_STRIP.segments


def test_el_estado_del_dispositivo_es_efimero_y_opcional() -> None:
    status = DeviceStatus(device_id=uuid4(), connected=False)

    assert status.rssi is None
    assert status.last_error is None


def test_el_dispositivo_descubierto_puede_no_anunciar_nombre() -> None:
    """Muchos controladores de esta clase se anuncian sin `local_name`."""
    discovered = DiscoveredDevice(address=ADDRESS)

    assert discovered.name is None
    assert discovered.rssi is None


def test_el_dispositivo_descubierto_conserva_el_orden_del_contrato() -> None:
    """README 16 devuelve {name, address, rssi} en ese orden."""
    discovered = DiscoveredDevice(name="ELK-BLEDOM", address=ADDRESS, rssi=-51)

    assert list(discovered.model_dump()) == ["name", "address", "rssi"]


class _FakeDiscovery:
    """Implementacion minima del puerto de descubrimiento, sin radio."""

    async def scan(self, timeout_s: float) -> Sequence[DiscoveredDevice]:
        return [DiscoveredDevice(name="ELK-BLEDOM", address=ADDRESS, rssi=-51)]


@pytest.mark.asyncio
async def test_un_escaner_sin_hardware_cumple_el_puerto_de_descubrimiento() -> None:
    scanner: DeviceDiscoveryPort = _FakeDiscovery()

    assert isinstance(scanner, DeviceDiscoveryPort)
    assert [device.address for device in await scanner.scan(1.0)] == [ADDRESS]


class _InMemoryDeviceRepository:
    """Repositorio en memoria. Solo existe para fijar la firma del puerto."""

    def __init__(self) -> None:
        self._devices: dict[UUID, Device] = {}
        self._states: dict[UUID, LightState] = {}

    def get(self, device_id: UUID) -> Device | None:
        return self._devices.get(device_id)

    def get_by_address(self, address: str) -> Device | None:
        return next((d for d in self._devices.values() if d.address == address), None)

    def list_enabled(self) -> Sequence[Device]:
        return [d for d in self._devices.values() if d.enabled]

    def upsert(self, device: Device) -> Device:
        self._devices[device.id] = device
        return device

    def load_state(self, device_id: UUID) -> LightState | None:
        return self._states.get(device_id)

    def save_state(self, device_id: UUID, state: LightState) -> None:
        self._states[device_id] = state


def test_el_repositorio_habla_tipos_de_dominio_y_no_sqlmodel() -> None:
    """La anotacion es el test: mypy falla si alguna firma deja de encajar.

    Corrige LED_ROOM_DATABASE_MODEL 50, que devolvia el `Device` de SQLModel.
    """
    repository: DeviceRepository = _InMemoryDeviceRepository()
    device = _device()

    repository.upsert(device)
    repository.save_state(device.id, LightState(power=True, color=RGBColor.from_hex("#7B00FF")))

    assert repository.get(device.id) == device
    assert repository.get_by_address(ADDRESS) == device
    assert list(repository.list_enabled()) == [device]

    state = repository.load_state(device.id)
    assert state is not None
    assert state.color.to_hex() == "#7B00FF"


def test_el_repositorio_no_conoce_dispositivos_deshabilitados() -> None:
    repository: DeviceRepository = _InMemoryDeviceRepository()
    repository.upsert(_device(enabled=False))

    assert list(repository.list_enabled()) == []
    assert repository.load_state(uuid4()) is None
