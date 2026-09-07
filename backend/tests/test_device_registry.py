"""El registro de adaptadores y la factoria que lo consulta (NEXT_STEPS A2)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.domain.devices.models import DeviceType
from backend.app.domain.devices.ports import DeviceDiscoveryPort, LightDevicePort
from backend.app.infrastructure.bluetooth.scanner import BleDeviceScanner
from backend.app.infrastructure.devices import factory, registry
from backend.app.infrastructure.devices.null_adapter import NullLightDeviceAdapter
from backend.app.infrastructure.devices.null_discovery import NullDiscoveryAdapter

# backend/tests/test_device_registry.py -> backend/tests -> backend -> raiz
REPO_ROOT = Path(__file__).resolve().parents[2]
DEVICES_ROOT = REPO_ROOT / "backend" / "app" / "infrastructure" / "devices"


@pytest.mark.parametrize("device_type", list(DeviceType), ids=[t.value for t in DeviceType])
def test_todo_tipo_de_dispositivo_tiene_constructor_registrado(device_type: DeviceType) -> None:
    """Añadir un miembro a DeviceType sin registrarlo debe romper la build.

    Es la razon de ser de la tabla: con un if/elif, el hueco solo aparecia en
    ejecucion y solo con esa configuracion puesta.
    """
    assert device_type in registry.ADAPTERS, (
        f"{device_type!r} no tiene entrada en ADAPTERS. Registre su constructor en "
        f"backend/app/infrastructure/devices/registry.py."
    )


def test_el_registro_no_contiene_tipos_que_no_existen() -> None:
    assert set(registry.ADAPTERS) == set(DeviceType)


@pytest.mark.parametrize("device_type", list(DeviceType), ids=[t.value for t in DeviceType])
def test_todo_tipo_de_dispositivo_declara_si_puede_descubrir(device_type: DeviceType) -> None:
    """La capacidad de descubrimiento es un dato del adaptador, no un `if` disperso.

    `GET /api/v1/system` la publica para que el cliente sepa ANTES de pulsar
    nada si este servidor puede encontrar hardware.
    """
    assert isinstance(registry.ADAPTERS[device_type].supports_discovery, bool)


def test_dar_de_alta_un_adaptador_sin_declarar_el_descubrimiento_no_construye() -> None:
    """Lo que hace obligatoria la declaracion es que el campo no tenga valor por defecto.

    Sin este test, alguien podria darle uno "para no tocar las entradas
    existentes" y el proximo adaptador entraria mintiendo por omision.
    """
    sin_hardware = registry.ADAPTERS[DeviceType.NULL]

    with pytest.raises(TypeError):
        registry.AdapterRegistration(  # type: ignore[call-arg]
            light_device=sin_hardware.light_device,
            discovery=sin_hardware.discovery,
        )


def test_el_adaptador_sin_hardware_declara_que_no_descubre() -> None:
    assert registry.ADAPTERS[DeviceType.NULL].supports_discovery is False
    assert factory.supports_discovery(Settings()) is False


def test_el_adaptador_ble_declara_que_descubre() -> None:
    """La declaracion describe la FAMILIA, no si su control ya existe.

    `factory.supports_discovery` no construye nada, asi que responde sin toparse
    con el `NotImplementedError` del adaptador de control.
    """
    assert registry.ADAPTERS[DeviceType.LOTUS_LANTERN].supports_discovery is True
    assert factory.supports_discovery(Settings(device_adapter=DeviceType.LOTUS_LANTERN)) is True


def test_el_registro_construye_el_adaptador_sin_hardware_para_null() -> None:
    registration = registry.ADAPTERS[DeviceType.NULL]

    assert isinstance(registration.light_device(Settings()), NullLightDeviceAdapter)
    assert isinstance(registration.discovery(Settings()), NullDiscoveryAdapter)


def test_null_es_el_adaptador_por_defecto() -> None:
    assert Settings().device_adapter is DeviceType.NULL


def test_el_constructor_ble_del_registro_crea_el_adaptador_real() -> None:
    """Ya no remite a la Fase 1: el protocolo se verifico contra el hardware.

    Construirlo no toca la radio -- eso solo pasa en `connect` --, asi que este
    test corre en cualquier host y en la CI.
    """
    from backend.app.infrastructure.bluetooth.lotus_lantern import LotusLanternBLEAdapter

    device = registry.ADAPTERS[DeviceType.LOTUS_LANTERN].light_device(Settings())

    assert isinstance(device, LotusLanternBLEAdapter)
    assert isinstance(device, LightDevicePort)


def test_el_escaner_ble_se_construye_por_separado_del_control() -> None:
    """Descubrir no es controlar, y por eso son dos campos independientes.

    Hoy los dos existen, pero siguen construyendose por separado: fue lo que
    permitio tener escaner real mientras el control esperaba al protocolo, y es
    lo que permitira a la proxima familia de hardware ir a su ritmo.
    """
    discovery = factory.build_device_discovery(Settings(device_adapter=DeviceType.LOTUS_LANTERN))

    assert isinstance(discovery, BleDeviceScanner)
    assert isinstance(discovery, DeviceDiscoveryPort)


def test_se_puede_descubrir_con_ble_mientras_se_controla_sin_hardware() -> None:
    """La configuracion que desbloquea la Fase 0 en el equipo del usuario.

    `LED_ROOM_DEVICE_ADAPTER=lotus_lantern` no arranca todavia (su
    `light_device` lanza), asi que sin esta separacion no habria forma de usar
    la radio del PC sin tumbar el servicio.
    """
    settings = Settings(
        device_adapter=DeviceType.NULL,
        device_discovery=DeviceType.LOTUS_LANTERN,
    )

    assert isinstance(factory.build_light_device(settings), LightDevicePort)
    assert isinstance(factory.build_device_discovery(settings), BleDeviceScanner)
    assert factory.supports_discovery(settings) is True


def test_la_factoria_explica_un_tipo_sin_constructor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regresion del camino defensivo: nunca un KeyError pelado en el arranque."""
    monkeypatch.setattr(registry, "ADAPTERS", {})

    with pytest.raises(ValueError, match="sin constructor registrado"):
        factory.build_light_device(Settings())


def test_la_factoria_devuelve_los_dos_puertos() -> None:
    settings = Settings()

    assert isinstance(factory.build_light_device(settings), LightDevicePort)
    assert isinstance(factory.build_device_discovery(settings), DeviceDiscoveryPort)


@pytest.mark.parametrize(
    "module_path",
    sorted(DEVICES_ROOT.glob("*.py")),
    ids=lambda path: path.name,
)
def test_la_infraestructura_de_dispositivos_no_importa_bleak(module_path: Path) -> None:
    """`bleak` solo puede aparecer en infrastructure/bluetooth/ (ARCHITECTURE 4).

    Sin esto, la CI y Windows sin radio dejarian de poder importar la factoria.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported = [node.module or ""]
        else:
            continue

        for name in imported:
            assert name != "bleak" and not name.startswith("bleak."), (
                f"{module_path.name}:{node.lineno} importa {name!r}."
            )
