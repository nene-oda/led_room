"""El escritor unico por dispositivo (NEXT_STEPS A2, ARCHITECTURE 4)."""

from __future__ import annotations

import asyncio
from itertools import pairwise

import pytest

from backend.app.config import Settings
from backend.app.domain.devices.models import DeviceTarget
from backend.app.domain.devices.ports import DeviceError, LightDevicePort
from backend.app.domain.lighting import LightFrame, RGBColor
from backend.app.infrastructure.devices.factory import build_light_device
from backend.app.infrastructure.devices.serialized import SerializedLightDevice
from backend.tests.doubles import RecordingLightDevice, overlapping

TARGET = DeviceTarget(address="BE:FF:00:11:22:33")

#: Margen para comparar dos relojes distintos (`monotonic` en el serializador,
#: `perf_counter` en el doble). Sin margen, el test seria un lanzamiento de dado.
CLOCK_TOLERANCE_S = 0.003


def _serialized(
    device: RecordingLightDevice,
    *,
    write_timeout_s: float = 5.0,
    min_write_interval_s: float = 0.0,
) -> SerializedLightDevice:
    return SerializedLightDevice(
        device,
        write_timeout_s=write_timeout_s,
        min_write_interval_s=min_write_interval_s,
    )


def test_el_doble_y_el_serializador_cumplen_el_puerto() -> None:
    device = RecordingLightDevice()

    assert isinstance(device, LightDevicePort)
    assert isinstance(_serialized(device), LightDevicePort)


@pytest.mark.asyncio
async def test_cien_escrituras_concurrentes_no_se_solapan() -> None:
    """La invariante del transporte: una sola escritura en vuelo."""
    device = RecordingLightDevice()
    serialized = _serialized(device)

    await asyncio.gather(*(serialized.set_color(index, 0, 0) for index in range(100)))

    assert len(device.writes) == 100, "El serializador no descarta escrituras: eso es throttling"
    assert overlapping(device.writes) == []


@pytest.mark.asyncio
async def test_apply_frame_ocupa_un_solo_turno() -> None:
    """Color y brillo del mismo fotograma no pueden separarse."""
    device = RecordingLightDevice()
    serialized = _serialized(device)
    frame = LightFrame(color=RGBColor.from_hex("#7B00FF"), brightness=60, duration_ms=50)

    await asyncio.gather(serialized.apply_frame(frame), serialized.set_power(True))

    assert device.operations == ["apply_frame:#7B00FF@60", "set_power:True"]
    assert overlapping(device.writes) == []


@pytest.mark.asyncio
async def test_una_escritura_colgada_expira_y_libera_el_cerrojo() -> None:
    """Sin timeout, un write colgado retiene el cerrojo y congela la aplicacion."""
    device = RecordingLightDevice()
    device.hangs = True
    serialized = _serialized(device, write_timeout_s=0.05)

    with pytest.raises(DeviceError, match="set_color"):
        await serialized.set_color(255, 0, 0)

    device.hangs = False
    await serialized.set_brightness(40)

    assert device.operations[-1] == "set_brightness:40"


@pytest.mark.asyncio
async def test_un_fallo_del_adaptador_se_propaga_y_libera_el_cerrojo() -> None:
    device = RecordingLightDevice()
    device.failure = DeviceError("el enlace se cayo")
    serialized = _serialized(device)

    with pytest.raises(DeviceError, match="el enlace se cayo"):
        await serialized.set_power(True)

    device.failure = None
    await serialized.set_power(False)

    assert device.operations == ["set_power:True", "set_power:False"]


@pytest.mark.asyncio
async def test_el_retardo_minimo_separa_las_tramas() -> None:
    """El retardo se duerme DENTRO del cerrojo: fuera, ambas se colarian juntas."""
    interval = 0.05
    device = RecordingLightDevice()
    serialized = _serialized(device, min_write_interval_s=interval)

    await asyncio.gather(*(serialized.set_brightness(value) for value in (10, 20, 30)))

    assert len(device.writes) == 3
    ordered = sorted(device.writes, key=lambda write: write.started_at)
    gaps = [second.started_at - first.finished_at for first, second in pairwise(ordered)]
    assert all(gap >= interval - CLOCK_TOLERANCE_S for gap in gaps), gaps


@pytest.mark.asyncio
async def test_la_primera_trama_no_espera() -> None:
    device = RecordingLightDevice()
    serialized = _serialized(device, min_write_interval_s=10.0)

    await asyncio.wait_for(serialized.set_power(True), timeout=1.0)

    assert device.operations == ["set_power:True"]


@pytest.mark.asyncio
async def test_las_capacidades_y_la_conexion_se_delegan() -> None:
    device = RecordingLightDevice()
    serialized = _serialized(device)

    await serialized.connect(TARGET)

    assert serialized.capabilities is device.capabilities
    assert device.connect_calls == 1
    assert device.targets == [TARGET], "El destino debe llegar intacto al adaptador envuelto"
    assert serialized.is_connected


@pytest.mark.asyncio
async def test_desconectar_dos_veces_es_seguro() -> None:
    """`main.py` llama a disconnect en el finally del lifespan, pase lo que pase."""
    device = RecordingLightDevice()
    serialized = _serialized(device)
    await serialized.connect(TARGET)

    await serialized.disconnect()
    await serialized.disconnect()

    assert device.disconnect_calls == 2
    assert not serialized.is_connected


@pytest.mark.parametrize(
    ("write_timeout_s", "min_write_interval_s"),
    [(0.0, 0.0), (-1.0, 0.0), (5.0, -0.1)],
)
def test_los_ajustes_invalidos_se_rechazan(
    write_timeout_s: float, min_write_interval_s: float
) -> None:
    with pytest.raises(ValueError):
        SerializedLightDevice(
            RecordingLightDevice(),
            write_timeout_s=write_timeout_s,
            min_write_interval_s=min_write_interval_s,
        )


def test_la_factoria_serializa_el_adaptador_que_construye() -> None:
    """Todo adaptador hereda el escritor unico: ninguno lo implementa a mano."""
    assert isinstance(build_light_device(Settings()), SerializedLightDevice)
