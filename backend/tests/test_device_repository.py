"""Repositorio de dispositivos sobre SQLite en memoria.

Sin hardware y sin archivos (LED_ROOM_DATABASE_MODEL 51). Lo que se prueba aqui
es el contrato del puerto de dominio, no SQLModel.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from backend.app.domain.devices.models import (
    SINGLE_COLOR_STRIP,
    Device,
    DeviceType,
)
from backend.app.domain.devices.repositories import DeviceRepository
from backend.app.domain.lighting import LightState, RGBColor
from backend.app.infrastructure.persistence.database import (
    IN_MEMORY_URL,
    create_all,
    create_database_engine,
)
from backend.app.infrastructure.persistence.models.device import DeviceRecord
from backend.app.infrastructure.persistence.repositories.device_repository import (
    SQLModelDeviceRepository,
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


@pytest.fixture
def repository(session: Session) -> DeviceRepository:
    # La anotacion es el puerto de DOMINIO a proposito: si la implementacion
    # deja de cumplirlo, lo detecta mypy antes que ningun test.
    return SQLModelDeviceRepository(session)


def _device(**overrides: object) -> Device:
    values: dict[str, object] = {
        "id": uuid4(),
        "name": "Bedroom LED",
        "adapter_type": DeviceType.LOTUS_LANTERN,
        "address": "BE:FF:00:11:22:33",
        "enabled": True,
        "auto_connect": True,
        "capabilities": SINGLE_COLOR_STRIP,
    }
    values.update(overrides)
    return Device.model_validate(values)


def _count_devices(session: Session) -> int:
    return int(session.execute(text("SELECT COUNT(*) FROM devices")).scalar_one())


def test_la_implementacion_cumple_el_puerto_del_dominio(repository: DeviceRepository) -> None:
    assert isinstance(repository, DeviceRepository)


def test_un_dispositivo_guardado_se_recupera_por_id(repository: DeviceRepository) -> None:
    device = _device()

    assert repository.upsert(device) == device
    assert repository.get(device.id) == device


def test_un_id_desconocido_devuelve_none(repository: DeviceRepository) -> None:
    assert repository.get(uuid4()) is None


def test_guardar_dos_veces_el_mismo_id_actualiza_en_vez_de_duplicar(
    repository: DeviceRepository, session: Session
) -> None:
    device = _device()
    repository.upsert(device)

    renamed = device.model_copy(update={"name": "Salon", "auto_connect": False})
    stored = repository.upsert(renamed)

    assert stored == renamed
    assert _count_devices(session) == 1


def test_el_mismo_controlador_descubierto_dos_veces_no_se_registra_dos_veces(
    repository: DeviceRepository, session: Session
) -> None:
    original = repository.upsert(_device())

    # Un segundo escaneo propone un id nuevo para la misma direccion: la
    # identidad de transporte manda y el id devuelto es el de la fila existente,
    # porque reescribir la clave primaria dejaria huerfanas las filas hijas.
    rediscovered = _device(id=uuid4(), name="Tira del dormitorio")
    stored = repository.upsert(rediscovered)

    assert stored.id == original.id
    assert stored.name == "Tira del dormitorio"
    assert _count_devices(session) == 1


def test_dos_dispositivos_sin_direccion_pueden_convivir(
    repository: DeviceRepository, session: Session
) -> None:
    # En SQLite los NULL son distintos entre si: el indice unico no impide
    # varios adaptadores nulos, que es justo lo que se quiere.
    repository.upsert(_device(adapter_type=DeviceType.NULL, address=None, name="A"))
    repository.upsert(_device(adapter_type=DeviceType.NULL, address=None, name="B"))

    assert _count_devices(session) == 2


def test_la_base_rechaza_una_direccion_duplicada_del_mismo_adaptador(session: Session) -> None:
    # Guardian de la migracion 0002: si el indice unico desaparece, la unica
    # defensa contra el duplicado seria la logica del upsert.
    for _ in range(2):
        session.add(
            DeviceRecord(
                id=uuid4(),
                name="LED",
                adapter_type="lotus_lantern",
                ble_address="BE:FF:00:11:22:33",
            )
        )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_se_resuelve_un_escaneo_contra_lo_ya_registrado(repository: DeviceRepository) -> None:
    device = repository.upsert(_device())

    assert repository.get_by_address("BE:FF:00:11:22:33") == device
    assert repository.get_by_address("00:00:00:00:00:00") is None


def test_un_dispositivo_deshabilitado_no_aparece_en_la_lista(
    repository: DeviceRepository,
) -> None:
    enabled = repository.upsert(_device(name="Salon", address="AA:AA:AA:AA:AA:AA"))
    repository.upsert(_device(name="Balcon", address="BB:BB:BB:BB:BB:BB", enabled=False))

    assert list(repository.list_enabled()) == [enabled]


def test_la_lista_sale_ordenada_por_nombre(repository: DeviceRepository) -> None:
    repository.upsert(_device(name="Salon", address="AA:AA:AA:AA:AA:AA"))
    repository.upsert(_device(name="Balcon", address="BB:BB:BB:BB:BB:BB"))

    assert [device.name for device in repository.list_enabled()] == ["Balcon", "Salon"]


def test_un_dispositivo_sin_estado_guardado_no_tiene_estado(
    repository: DeviceRepository,
) -> None:
    device = repository.upsert(_device())

    assert repository.load_state(device.id) is None


def test_el_estado_deseado_sobrevive_a_una_relectura(repository: DeviceRepository) -> None:
    device = repository.upsert(_device())
    state = LightState(power=True, color=RGBColor.from_hex("#7b00ff"), brightness=20)

    repository.save_state(device.id, state)

    assert repository.load_state(device.id) == state


def test_guardar_el_estado_dos_veces_no_crea_una_segunda_fila(
    repository: DeviceRepository, session: Session
) -> None:
    device = repository.upsert(_device())

    repository.save_state(device.id, LightState(power=True))
    repository.save_state(device.id, LightState(power=False, brightness=10))

    assert session.execute(text("SELECT COUNT(*) FROM device_state")).scalar_one() == 1
    assert repository.load_state(device.id) == LightState(power=False, brightness=10)


def test_el_color_llega_a_la_base_en_mayusculas(
    repository: DeviceRepository, session: Session
) -> None:
    # Regresion del CHECK ... GLOB de device_state, que distingue mayusculas.
    device = repository.upsert(_device())

    repository.save_state(device.id, LightState(color=RGBColor(r=123, g=0, b=255)))

    stored = session.execute(
        text("SELECT color_hex FROM device_state WHERE device_id = :d"),
        {"d": device.id.hex},
    ).scalar_one()
    assert stored == "#7B00FF"
