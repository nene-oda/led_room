from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain.devices.models import DeviceStatus
from backend.app.domain.lighting import LightState, RGBColor
from backend.app.domain.state import EffectStatus, GlobalState, SceneStatus


def test_el_estado_inicial_no_tiene_dispositivo_ni_efecto_ni_escena() -> None:
    state = GlobalState()

    assert state.version == 0
    assert state.device is None
    assert state.effect is None
    assert state.scene is None


def test_el_estado_inicial_de_la_luz_coincide_con_el_de_la_base() -> None:
    """`DeviceStateRecord` arranca apagado, en #FFFFFF y al 100 %."""
    light = GlobalState().light

    assert not light.power
    assert light.color.to_hex() == "#FFFFFF"
    assert light.brightness == 100


def test_la_forma_del_estado_es_la_del_readme_31() -> None:
    assert list(GlobalState().model_dump()) == ["version", "device", "light", "effect", "scene"]
    assert list(LightState().model_dump()) == ["power", "color", "brightness"]
    assert list(EffectStatus(running=True, id=uuid4()).model_dump()) == ["running", "id"]
    assert list(SceneStatus(id=uuid4()).model_dump()) == ["id"]


def _assign(target: object, attribute: str, value: object) -> None:
    """Asignacion indirecta: probar la inmutabilidad sin discutir con el verificador."""
    setattr(target, attribute, value)


def test_el_estado_global_es_inmutable() -> None:
    """El store publica un estado nuevo; nadie muta el que ya vieron los clientes."""
    state = GlobalState()

    with pytest.raises(ValidationError):
        _assign(state, "version", 7)


def test_la_version_avanza_creando_un_estado_nuevo() -> None:
    """El store no muta: produce la version siguiente (NEXT_STEPS A4)."""
    state = GlobalState()

    updated = state.model_copy(
        update={
            "version": state.version + 1,
            "light": state.light.model_copy(update={"power": True}),
        }
    )

    assert updated.version == 1
    assert updated.light.power
    assert state.version == 0
    assert not state.light.power


def test_la_version_no_puede_ser_negativa() -> None:
    with pytest.raises(ValidationError):
        GlobalState(version=-1)


def test_el_estado_transporta_el_dispositivo_y_la_luz() -> None:
    device_id = uuid4()
    state = GlobalState(
        version=3,
        device=DeviceStatus(device_id=device_id, connected=True, rssi=-51),
        light=LightState(power=True, color=RGBColor.from_hex("#7B00FF"), brightness=60),
    )

    assert state.device is not None
    assert state.device.connected
    assert state.light.brightness == 60
    assert state.light.color.to_hex() == "#7B00FF"


@pytest.mark.parametrize("brightness", [-1, 101])
def test_el_estado_de_la_luz_rechaza_brillos_fuera_de_porcentaje(brightness: int) -> None:
    with pytest.raises(ValidationError):
        LightState(brightness=brightness)
