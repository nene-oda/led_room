"""El unico titular mutable del estado autoritativo (NEXT_STEPS A4)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from backend.app.application.state_store import StateStore
from backend.app.domain.devices.models import DeviceStatus
from backend.app.domain.events import (
    DomainEvent,
    EventType,
    LightBrightnessChanged,
    LightPowerChanged,
    StateSnapshot,
)
from backend.app.domain.lighting import LightState, RGBColor
from backend.app.domain.state import GlobalState
from backend.tests.doubles import RecordingEventPublisher, SkewedEventPublisher


def _store() -> tuple[StateStore, RecordingEventPublisher]:
    publisher = RecordingEventPublisher()
    return StateStore(publisher), publisher


@pytest.mark.asyncio
async def test_el_estado_inicial_es_la_version_cero_sin_dispositivo() -> None:
    store, publisher = _store()

    state = await store.snapshot()

    assert state == GlobalState()
    assert state.version == 0
    assert state.device is None
    assert publisher.events == []


@pytest.mark.asyncio
async def test_una_mutacion_aceptada_incrementa_la_version_y_publica_su_evento() -> None:
    store, publisher = _store()

    async with store.mutate() as draft:
        draft.set_light(LightState(power=True))
        draft.event = LightPowerChanged(power=True)

    assert (await store.snapshot()).version == 1
    assert (await store.snapshot()).light.power is True
    assert publisher.events == [LightPowerChanged(power=True)]


@pytest.mark.asyncio
async def test_el_llamante_ve_el_estado_confirmado_al_salir_del_bloque() -> None:
    """Sin esto, un servicio tendria que volver a pedir el snapshot para responder."""
    store, _ = _store()

    async with store.mutate() as draft:
        draft.set_light(LightState(brightness=42))

    assert draft.state.version == 1
    assert draft.state.light.brightness == 42


@pytest.mark.asyncio
async def test_un_fallo_dentro_de_la_mutacion_no_cambia_el_estado_ni_publica() -> None:
    """La regla que sostiene el orden de operaciones (NEXT_STEPS A4).

    La escritura en el dispositivo ocurre dentro del bloque: si el enlace BLE se
    cae, publicar de todos modos desincronizaria a los clientes justo cuando la
    sincronia importa.
    """
    store, publisher = _store()

    with pytest.raises(RuntimeError, match="enlace caido"):
        async with store.mutate() as draft:
            draft.set_light(LightState(power=True))
            draft.event = LightPowerChanged(power=True)
            raise RuntimeError("enlace caido")

    state = await store.snapshot()
    assert state.version == 0
    assert state.light.power is False
    assert publisher.events == []


@pytest.mark.asyncio
async def test_una_mutacion_que_no_cambia_nada_no_gasta_version_ni_publica() -> None:
    """Es lo que hace idempotente un `disconnect` sobre algo ya desconectado."""
    store, publisher = _store()

    async with store.mutate() as draft:
        draft.event = LightPowerChanged(power=True)

    assert (await store.snapshot()).version == 0
    assert publisher.events == []


@pytest.mark.asyncio
async def test_cincuenta_mutaciones_concurrentes_dejan_el_store_coherente() -> None:
    """El cerrojo impide actualizaciones perdidas: cada una lee lo que dejo la anterior.

    El `await` entre leer y escribir el incremento no es adorno: es lo unico que
    hace que este test pruebe algo. Sin el, el cuerpo del `async with` es
    sincero de principio a fin, ninguna corrutina cede el control y el resultado
    seria 50 tambien sin cerrojo. Con el, quitar el cerrojo da 1.

    Y es fiel a la realidad: el cuerpo de una mutacion contiene la escritura al
    dispositivo, que es exactamente un punto de suspension en ese sitio.
    """
    publisher = RecordingEventPublisher()
    store = StateStore(publisher, initial=GlobalState(light=LightState(brightness=0)))

    async def increment() -> None:
        async with store.mutate() as draft:
            current = draft.state.light
            await asyncio.sleep(0)  # donde va la escritura al dispositivo
            draft.set_light(
                LightState(
                    power=current.power,
                    color=current.color,
                    brightness=current.brightness + 1,
                )
            )
            draft.event = LightBrightnessChanged(brightness=current.brightness + 1)

    await asyncio.gather(*(increment() for _ in range(50)))

    state = await store.snapshot()
    assert state.version == 50
    assert state.light.brightness == 50
    assert len(publisher.events) == 50


@pytest.mark.asyncio
async def test_los_eventos_se_publican_en_el_orden_de_las_versiones() -> None:
    """Publicar fuera del cerrojo permitiria aplicar un cambio viejo tras uno nuevo.

    El publicador tarda distinto en cada frame a proposito: uno instantaneo no
    puede reordenar nada, asi que la version anterior de este test pasaba igual
    sin cerrojo. Y se comprueba la secuencia entera, no solo el ultimo valor: lo
    que rompe a un cliente no es acabar mal, es aplicar el evento 7 despues del
    12.
    """
    publisher = SkewedEventPublisher()
    store = StateStore(publisher)

    async def bump(value: int) -> None:
        async with store.mutate() as draft:
            draft.set_light(LightState(brightness=value))
            draft.event = LightBrightnessChanged(brightness=draft.state.light.brightness)

    await asyncio.gather(*(bump(value) for value in range(1, 21)))

    published = [
        event.brightness for event in publisher.events if isinstance(event, LightBrightnessChanged)
    ]
    assert published == list(range(1, 21))
    assert publisher.versions == list(range(1, 21)), "El sobre debe llevar la version que confirma"
    assert published[-1] == (await store.snapshot()).light.brightness


@pytest.mark.asyncio
async def test_un_publicador_que_falla_no_deshace_el_cambio_ya_aplicado() -> None:
    """`EventPublisher` promete no lanzar; el store lo hace cumplir en la frontera."""
    store, publisher = _store()
    publisher.failure = RuntimeError("cliente WebSocket caido")

    async with store.mutate() as draft:
        draft.set_light(LightState(power=True))
        draft.event = LightPowerChanged(power=True)

    state = await store.snapshot()
    assert state.version == 1
    assert state.light.power is True


@pytest.mark.asyncio
async def test_el_snapshot_publicado_lleva_el_estado_completo_y_su_version() -> None:
    store, publisher = _store()
    device_id = uuid4()

    async with store.mutate() as draft:
        draft.set_device(DeviceStatus(device_id=device_id, connected=True))
        draft.set_light(LightState(power=True, color=RGBColor.from_hex("#7B00FF"), brightness=20))

    await store.publish_snapshot()

    snapshot = publisher.events[-1]
    assert isinstance(snapshot, StateSnapshot)
    assert snapshot.type is EventType.STATE_SNAPSHOT
    assert snapshot.state == await store.snapshot()
    assert snapshot.state.version == 1


@pytest.mark.asyncio
async def test_el_store_solo_expone_metodos_async() -> None:
    """Una dependencia sincrona de FastAPI corre en el threadpool.

    Si el store tuviera metodos sincronos, desde alli se podria mutar el estado
    global fuera del bucle de eventos y sin el cerrojo.
    """
    store, _ = _store()

    public = [name for name in dir(store) if not name.startswith("_")]

    assert public
    for name in public:
        member = getattr(store, name)
        assert asyncio.iscoroutinefunction(member) or hasattr(member, "__wrapped__"), (
            f"StateStore.{name} no es asincrono"
        )


def test_el_borrador_solo_admite_los_campos_con_caso_de_uso() -> None:
    """Un campo de `GlobalState` sin caso de uso propietario no tiene setter.

    Cada uno tiene exactamente un llamante legitimo: `set_effect` es de
    `application/effect_service.py` (Fase 5) y `set_scene` de
    `application/scene_service.py` (Fase 6). El resto de `GlobalState` --
    `version` -- lo gobierna el store y por eso no aparece aqui.
    """
    from backend.app.application.state_store import StateDraft

    draft = StateDraft(GlobalState())
    setters = {name for name in dir(draft) if name.startswith("set_")}

    assert setters == {"set_light", "set_device", "set_effect", "set_scene"}
    assert isinstance(draft.event, DomainEvent) is False


@pytest.mark.asyncio
async def test_hold_impide_que_una_mutacion_se_cuele_mientras_se_hidrata() -> None:
    """B1: alta del cliente y snapshot deben ser atomicos frente a la difusion.

    Sin esto, un cliente recien conectado podia recibir
    `['light.power.changed', 'state.snapshot']` -- el snapshot capturado ANTES
    del cambio, entregado DESPUES -- y quedarse con `power: false` de forma
    permanente. Invertir el orden (mandar el snapshot y dar de alta luego) no
    sirve: perderia los eventos de esa misma ventana.
    """
    store, publisher = _store()
    orden: list[str] = []

    async def hidrata() -> None:
        async with store.hold() as state:
            orden.append(f"snapshot:v{state.version}")
            # Cualquier punto de suspension dentro del bloque: el cerrojo debe
            # aguantar igualmente.
            await asyncio.sleep(0.01)
            orden.append("alta")

    async def enciende() -> None:
        await asyncio.sleep(0)
        async with store.mutate() as draft:
            draft.set_light(LightState(power=True))
            draft.event = LightPowerChanged(power=True)
        orden.append("evento")

    await asyncio.gather(hidrata(), enciende())

    assert orden == ["snapshot:v0", "alta", "evento"]
    assert publisher.versions == [1]


@pytest.mark.asyncio
async def test_hold_cede_el_estado_ya_confirmado() -> None:
    store, _ = _store()
    async with store.mutate() as draft:
        draft.set_light(LightState(brightness=7))

    async with store.hold() as state:
        assert state.version == 1
        assert state.light.brightness == 7
