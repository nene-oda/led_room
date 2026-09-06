"""Esquema, constraints y PRAGMA de SQLite.

Sin hardware y sin archivos: base en memoria con StaticPool
(LED_ROOM_DATABASE_MODEL 51).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from backend.app.infrastructure.persistence.database import (
    IN_MEMORY_URL,
    create_all,
    create_database_engine,
)
from backend.app.infrastructure.persistence.models import (
    DeviceCapabilitiesRecord,
    DeviceRecord,
    DeviceStateRecord,
    EffectRecord,
    EffectStepRecord,
    ProfileRecord,
    ProfileSceneRecord,
    SceneRecord,
    SceneTargetRecord,
)

EXPECTED_TABLES = {
    "devices",
    "device_capabilities",
    "device_state",
    "effects",
    "effect_steps",
    "scenes",
    "scene_targets",
    "profiles",
    "profile_scenes",
    "schedules",
}


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


def test_el_esquema_tiene_las_diez_tablas(engine: Engine) -> None:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'")
        found = {row[0] for row in rows}
    assert found >= EXPECTED_TABLES


def test_las_claves_foraneas_estan_activadas(engine: Engine) -> None:
    # PRAGMA foreign_keys es por CONEXION y viene apagado. Sin el listener, cada
    # ON DELETE CASCADE del esquema seria decorativo.
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_una_base_en_memoria_no_intenta_activar_wal(engine: Engine) -> None:
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "memory"


def test_guardar_y_releer_un_dispositivo_completo(session: Session) -> None:
    device = DeviceRecord(name="Bedroom LED", adapter_type="lotus_lantern", ble_name="ELK-BLEDOM")
    device.capabilities = DeviceCapabilitiesRecord(supports_effects=True, music_mode=True)
    device.state = DeviceStateRecord(color_hex="#7B00FF", brightness=55)
    session.add(device)
    session.commit()
    session.refresh(device)

    assert device.capabilities is not None
    assert device.capabilities.addressable is False
    assert device.state is not None
    assert device.state.brightness == 55


def test_las_marcas_de_tiempo_vuelven_con_zona_horaria(session: Session) -> None:
    device = DeviceRecord(name="LED", adapter_type="null")
    session.add(device)
    session.commit()
    session.refresh(device)

    # SQLite no guarda el desplazamiento: sin el TypeDecorator propio esto
    # devolveria un datetime naive y compararlo con utc_now() reventaria.
    offset = device.created_at.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


def _insert_state(session: Session, device: DeviceRecord, color: str, brightness: int) -> None:
    session.execute(
        text(
            "INSERT INTO device_state (device_id, power, color_hex, brightness, updated_at)"
            " VALUES (:d, 0, :c, :b, '2026-01-01 00:00:00')"
        ),
        {"d": device.id.hex, "c": color, "b": brightness},
    )
    session.commit()


def test_el_brillo_fuera_de_rango_lo_rechaza_la_base(session: Session) -> None:
    device = DeviceRecord(name="LED", adapter_type="null")
    session.add(device)
    session.commit()

    with pytest.raises(IntegrityError):
        _insert_state(session, device, "#FFFFFF", 101)
    session.rollback()


def test_el_color_debe_ir_en_mayusculas(session: Session) -> None:
    # ARCHITECTURE 3.2 fija #RRGGBB en mayusculas como forma canonica.
    device = DeviceRecord(name="LED", adapter_type="null")
    session.add(device)
    session.commit()

    with pytest.raises(IntegrityError):
        _insert_state(session, device, "#7b00ff", 50)
    session.rollback()


def test_no_se_repite_la_posicion_dentro_de_un_efecto(session: Session) -> None:
    effect = EffectRecord(name="Cyberpunk", type="SMOOTH_CYCLE")
    effect.steps = [
        EffectStepRecord(position=0, color_hex="#009DFF"),
        EffectStepRecord(position=0, color_hex="#7B00FF"),
    ]
    session.add(effect)

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_los_pasos_salen_ordenados_por_posicion(session: Session) -> None:
    effect = EffectRecord(name="Sunset", type="SMOOTH_CYCLE")
    effect.steps = [
        EffectStepRecord(position=2, color_hex="#FF4040"),
        EffectStepRecord(position=0, color_hex="#FFE259"),
        EffectStepRecord(position=1, color_hex="#FF9A3C"),
    ]
    session.add(effect)
    session.commit()
    session.refresh(effect)

    assert [step.position for step in effect.steps] == [0, 1, 2]


def test_una_escena_no_apunta_dos_veces_al_mismo_dispositivo(session: Session) -> None:
    device = DeviceRecord(name="LED", adapter_type="null")
    effect = EffectRecord(name="Static", type="STATIC")
    scene = SceneRecord(name="Gaming Night")
    session.add_all([device, effect, scene])
    session.commit()

    session.add(SceneTargetRecord(scene_id=scene.id, device_id=device.id, effect_id=effect.id))
    session.commit()

    session.add(SceneTargetRecord(scene_id=scene.id, device_id=device.id, effect_id=effect.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_borrar_un_dispositivo_arrastra_capacidades_estado_y_objetivos(session: Session) -> None:
    device = DeviceRecord(name="LED", adapter_type="null")
    device.capabilities = DeviceCapabilitiesRecord()
    device.state = DeviceStateRecord()
    effect = EffectRecord(name="Static", type="STATIC")
    scene = SceneRecord(name="Relax")
    session.add_all([device, effect, scene])
    session.commit()
    session.add(SceneTargetRecord(scene_id=scene.id, device_id=device.id, effect_id=effect.id))
    session.commit()

    session.execute(text("DELETE FROM devices WHERE id = :d"), {"d": device.id.hex})
    session.commit()

    for table in ("device_capabilities", "device_state", "scene_targets"):
        assert session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0


def test_no_se_borra_un_efecto_que_una_escena_usa(session: Session) -> None:
    device = DeviceRecord(name="LED", adapter_type="null")
    effect = EffectRecord(name="Cyberpunk", type="SMOOTH_CYCLE")
    scene = SceneRecord(name="Gaming Night")
    session.add_all([device, effect, scene])
    session.commit()
    session.add(SceneTargetRecord(scene_id=scene.id, device_id=device.id, effect_id=effect.id))
    session.commit()

    with pytest.raises(IntegrityError):
        session.execute(text("DELETE FROM effects WHERE id = :e"), {"e": effect.id.hex})
        session.commit()
    session.rollback()


def test_un_horario_apunta_a_una_escena_o_a_un_perfil_pero_no_a_ambos(session: Session) -> None:
    scene = SceneRecord(name="Sleep")
    profile = ProfileRecord(name="Sleep")
    session.add_all([scene, profile])
    session.commit()

    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO schedules"
                " (id, name, enabled, at_time, scene_id, profile_id, created_at, updated_at)"
                " VALUES ('0', 'noche', 1, '23:30', :s, :p,"
                " '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            ),
            {"s": scene.id.hex, "p": profile.id.hex},
        )
        session.commit()
    session.rollback()


def test_una_escena_puede_estar_en_varios_perfiles(session: Session) -> None:
    scene = SceneRecord(name="Sunset")
    gaming = ProfileRecord(name="Gaming")
    relax = ProfileRecord(name="Relax")
    session.add_all([scene, gaming, relax])
    session.commit()

    session.add_all(
        [
            ProfileSceneRecord(profile_id=gaming.id, scene_id=scene.id, position=0),
            ProfileSceneRecord(profile_id=relax.id, scene_id=scene.id, position=1),
        ]
    )
    session.commit()
    session.refresh(scene)

    assert len(scene.profile_links) == 2
