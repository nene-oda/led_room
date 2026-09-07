"""Traduccion dominio <-> filas de dispositivos.

Base en memoria con StaticPool, sin archivos y sin hardware
(LED_ROOM_DATABASE_MODEL 51).
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session

from backend.app.domain.devices.models import Device, DeviceCapabilities, DeviceType
from backend.app.domain.lighting import LightState, RGBColor
from backend.app.infrastructure.persistence.database import (
    IN_MEMORY_URL,
    create_all,
    create_database_engine,
)
from backend.app.infrastructure.persistence.mappers.device import (
    DeviceMappingError,
    adapter_type_to_column,
    apply_device_to_record,
    apply_state_to_record,
    device_to_domain,
    state_to_domain,
)
from backend.app.infrastructure.persistence.models.device import (
    DeviceCapabilitiesRecord,
    DeviceRecord,
    DeviceStateRecord,
)

#: Cada campo es lo CONTRARIO del valor por defecto de su columna
#: (`supports_rgb` y `supports_brightness` nacen en True; los otros cinco en
#: False). Asi, si alguien añade una capacidad y olvida volcarla en
#: `_apply_capabilities`, el valor por defecto de la columna no coincide con el
#: del dominio y el round-trip falla en vez de pasar por casualidad.
OPPOSITE_OF_COLUMN_DEFAULTS = DeviceCapabilities(
    rgb=False,
    brightness=False,
    effects=True,
    addressable=True,
    segments=True,
    white_channel=True,
    music_mode=True,
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = create_database_engine(url=IN_MEMORY_URL)
    create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def _domain_device(**overrides: object) -> Device:
    values: dict[str, object] = {
        "id": uuid4(),
        "name": "Bedroom LED",
        "adapter_type": DeviceType.LOTUS_LANTERN,
        "address": "BE:FF:00:11:22:33",
        "enabled": True,
        "auto_connect": False,
        "capabilities": OPPOSITE_OF_COLUMN_DEFAULTS,
    }
    values.update(overrides)
    return Device.model_validate(values)


def _persist(session: Session, device: Device) -> DeviceRecord:
    record = DeviceRecord(id=device.id)
    apply_device_to_record(record, device)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def test_el_viaje_de_ida_y_vuelta_conserva_las_siete_capacidades(session: Session) -> None:
    device = _domain_device()

    restored = device_to_domain(_persist(session, device))

    assert restored == device
    assert restored.capabilities == OPPOSITE_OF_COLUMN_DEFAULTS


def test_las_capacidades_viajan_a_las_columnas_con_prefijo(session: Session) -> None:
    # El unico test que puede nombrar `supports_*`: si esa cadena aparece fuera
    # del mapper (o de aqui), la frontera de persistencia esta rota.
    record = _persist(session, _domain_device())

    assert record.capabilities is not None
    assert record.capabilities.supports_rgb is False
    assert record.capabilities.supports_brightness is False
    assert record.capabilities.supports_effects is True
    assert record.capabilities.supports_segments is True


def test_el_adaptador_se_guarda_con_el_vocabulario_del_dominio(session: Session) -> None:
    record = _persist(session, _domain_device(adapter_type=DeviceType.NULL))

    assert record.adapter_type == "null"
    assert adapter_type_to_column(DeviceType.LOTUS_LANTERN) == "lotus_lantern"


def test_un_adapter_type_desconocido_falla_con_un_mensaje_explicito(session: Session) -> None:
    record = _persist(session, _domain_device())
    # Una fila escrita a mano o por una version con mas adaptadores que esta.
    session.execute(
        text("UPDATE devices SET adapter_type = 'wled' WHERE id = :d"),
        {"d": record.id.hex},
    )
    session.commit()

    stale = session.get(DeviceRecord, record.id)
    assert stale is not None

    with pytest.raises(DeviceMappingError) as error:
        device_to_domain(stale)

    assert "wled" in str(error.value)
    assert "lotus_lantern" in str(error.value)


def test_un_dispositivo_sin_capacidades_no_se_traduce_en_silencio(session: Session) -> None:
    record = DeviceRecord(id=uuid4(), name="LED", adapter_type="null")
    session.add(record)
    session.commit()

    with pytest.raises(DeviceMappingError):
        device_to_domain(record)


def test_actualizar_no_toca_la_clave_primaria_ni_el_nombre_ble(session: Session) -> None:
    device = _domain_device()
    record = _persist(session, device)
    record.ble_name = "ELK-BLEDOM"
    session.commit()

    apply_device_to_record(record, device.model_copy(update={"id": uuid4(), "name": "Salon"}))
    session.commit()
    session.refresh(record)

    # El `id` lo decide la fila, no el argumento: reescribirlo dejaria huerfanas
    # las filas hijas. Y `ble_name` no esta en el dominio, asi que se preserva.
    assert record.id == device.id
    assert record.ble_name == "ELK-BLEDOM"
    assert record.name == "Salon"


def test_guardar_un_color_en_minusculas_lo_deja_en_mayusculas(session: Session) -> None:
    # Regresion del CHECK ... GLOB '#[0-9A-F]...' de device_state: con GLOB
    # (que si distingue mayusculas) guardar '#7b00ff' lanzaria IntegrityError.
    device = _domain_device()
    record = _persist(session, device)

    state = LightState(power=True, color=RGBColor.from_hex("#7b00ff"), brightness=55)
    state_record = DeviceStateRecord(device_id=record.id)
    apply_state_to_record(state_record, state)
    session.add(state_record)
    session.commit()

    stored = session.execute(
        text("SELECT color_hex FROM device_state WHERE device_id = :d"),
        {"d": record.id.hex},
    ).scalar_one()
    assert stored == "#7B00FF"
    assert state_to_domain(state_record) == state


def test_el_estado_por_defecto_de_la_fila_coincide_con_el_del_dominio(session: Session) -> None:
    record = _persist(session, _domain_device())
    state_record = DeviceStateRecord(device_id=record.id)
    session.add(state_record)
    session.commit()

    # Hidratar desde una base recien creada y arrancar sin base deben dar
    # exactamente el mismo estado.
    assert state_to_domain(state_record) == LightState()


def test_un_color_corrupto_no_se_confunde_con_una_peticion_invalida(session: Session) -> None:
    # DeviceMappingError NO hereda de ValueError: la politica de errores manda
    # los ValueError de rango a 422, y una fila corrupta es un 500.
    record = DeviceStateRecord(device_id=uuid4(), color_hex="nada")

    with pytest.raises(DeviceMappingError) as error:
        state_to_domain(record)

    assert not isinstance(error.value, ValueError)


def test_las_capacidades_ausentes_se_crean_al_volcar(session: Session) -> None:
    record = DeviceRecord(id=uuid4())
    apply_device_to_record(record, _domain_device())

    assert isinstance(record.capabilities, DeviceCapabilitiesRecord)
