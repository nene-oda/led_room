from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.application.ports import EventPublisher
from backend.app.domain.events import (
    DeviceConnected,
    DeviceDisconnected,
    DomainEvent,
    EffectStarted,
    EffectStopped,
    ErrorOccurred,
    EventType,
    LightBrightnessChanged,
    LightColorChanged,
    LightPowerChanged,
    SceneActivated,
    StateSnapshot,
)
from backend.app.domain.lighting import RGBColor
from backend.app.domain.state import GlobalState

#: Lista inmutable de ARCHITECTURE 3.6 / README 17. Esta escrita a mano a
#: proposito: derivarla del enum haria que el test se moviera con el codigo.
FROZEN_EVENT_NAMES = {
    "device.connected",
    "device.disconnected",
    "light.power.changed",
    "light.color.changed",
    "light.brightness.changed",
    "effect.started",
    "effect.stopped",
    "scene.activated",
}

#: Ampliaciones acordadas en NEXT_STEPS A4 y A6, pendientes de reflejar en
#: ARCHITECTURE 3.6.
EXTENSION_EVENT_NAMES = {"state.snapshot", "error"}


def test_los_nombres_congelados_siguen_existiendo() -> None:
    declarados = {event.value for event in EventType}
    assert declarados >= FROZEN_EVENT_NAMES


def test_no_hay_nombres_de_evento_inventados() -> None:
    """Añadir un evento obliga a documentarlo, no solo a escribirlo."""
    assert {event.value for event in EventType} == FROZEN_EVENT_NAMES | EXTENSION_EVENT_NAMES


@pytest.mark.parametrize(
    ("event", "expected_type"),
    [
        (DeviceConnected(device_id=uuid4()), EventType.DEVICE_CONNECTED),
        (DeviceDisconnected(device_id=uuid4()), EventType.DEVICE_DISCONNECTED),
        (LightPowerChanged(power=True), EventType.LIGHT_POWER_CHANGED),
        (LightColorChanged(color=RGBColor(r=1, g=2, b=3)), EventType.LIGHT_COLOR_CHANGED),
        (LightBrightnessChanged(brightness=60), EventType.LIGHT_BRIGHTNESS_CHANGED),
        (EffectStarted(effect_id=uuid4()), EventType.EFFECT_STARTED),
        (EffectStopped(effect_id=uuid4()), EventType.EFFECT_STOPPED),
        (SceneActivated(scene_id=uuid4()), EventType.SCENE_ACTIVATED),
        (StateSnapshot(state=GlobalState()), EventType.STATE_SNAPSHOT),
        (ErrorOccurred(code="device_not_connected", message="sin enlace"), EventType.ERROR),
    ],
)
def test_cada_evento_lleva_su_propio_nombre(event: DomainEvent, expected_type: EventType) -> None:
    assert event.type == expected_type
    assert isinstance(event, DomainEvent)


def test_un_evento_no_puede_usurpar_el_nombre_de_otro() -> None:
    with pytest.raises(ValidationError):
        LightPowerChanged.model_validate({"type": "scene.activated", "power": True})


def _assign(target: object, attribute: str, value: object) -> None:
    """Asignacion indirecta: probar la inmutabilidad sin discutir con el verificador."""
    setattr(target, attribute, value)


def test_los_eventos_son_inmutables() -> None:
    event = LightPowerChanged(power=True)

    with pytest.raises(ValidationError):
        _assign(event, "power", False)


def test_el_color_viaja_como_tipo_de_dominio_no_como_cadena() -> None:
    """La serializacion (#RRGGBB o {r,g,b}) la decide el transporte, no el dominio."""
    event = LightColorChanged(color=RGBColor.from_hex("#7B00FF"))

    assert event.color == RGBColor(r=123, g=0, b=255)


def test_el_brillo_del_evento_respeta_el_porcentaje() -> None:
    with pytest.raises(ValidationError):
        LightBrightnessChanged(brightness=101)


def test_el_snapshot_transporta_el_estado_completo() -> None:
    state = GlobalState(version=4)

    assert StateSnapshot(state=state).state.version == 4


class _RecordingPublisher:
    """Publicador de prueba: la aplicacion no distingue esto de un WebSocket."""

    def __init__(self) -> None:
        self.events: list[tuple[DomainEvent, int]] = []

    async def publish(self, event: DomainEvent, version: int) -> None:
        self.events.append((event, version))


@pytest.mark.asyncio
async def test_cualquier_publicador_estructural_cumple_el_puerto() -> None:
    publisher: EventPublisher = _RecordingPublisher()

    await publisher.publish(LightPowerChanged(power=True), 7)

    assert isinstance(publisher, EventPublisher)
    assert isinstance(publisher, _RecordingPublisher)
    assert publisher.events == [(LightPowerChanged(power=True), 7)]
