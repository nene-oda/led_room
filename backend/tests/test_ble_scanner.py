"""El descubrimiento BLE real, probado sin radio (NEXT_STEPS 4.1).

Ningun test de aqui necesita hardware: `BleDeviceScanner` recibe la funcion de
escaneo inyectada, asi que la suite corre igual en la CI y en un portatil con el
Bluetooth apagado. Lo que si son de verdad son los tipos de Bleak que se le
devuelven -- `BLEDevice` y `AdvertisementData` --, porque la traduccion a dominio
es justo lo que se esta comprobando: un doble con otra forma probaria el doble.
"""

from __future__ import annotations

import asyncio

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import (
    BleakBluetoothNotAvailableError,
    BleakBluetoothNotAvailableReason,
    BleakError,
)

from backend.app.domain.devices.models import DiscoveredDevice
from backend.app.domain.devices.ports import (
    DeviceDiscoveryPort,
    DeviceError,
    DeviceUnavailableError,
)
from backend.app.infrastructure.bluetooth.scanner import (
    Advertisements,
    BleDeviceScanner,
    ScanFunction,
)


def advertisement(*, rssi: int, local_name: str | None = None) -> AdvertisementData:
    return AdvertisementData(
        local_name=local_name,
        manufacturer_data={},
        service_data={},
        service_uuids=[],
        tx_power=None,
        rssi=rssi,
        platform_data=(),
    )


def found(*entries: tuple[str, str | None, int]) -> Advertisements:
    """Construye lo que devuelve `BleakScanner.discover(return_adv=True)`."""
    return {
        address: (
            BLEDevice(address, name, None),
            advertisement(rssi=rssi, local_name=name),
        )
        for address, name, rssi in entries
    }


def returning(advertisements: Advertisements) -> ScanFunction:
    async def discover(timeout_s: float) -> Advertisements:
        return advertisements

    return discover


def test_el_escaner_ble_cumple_el_puerto_de_descubrimiento() -> None:
    assert isinstance(BleDeviceScanner(), DeviceDiscoveryPort)


@pytest.mark.asyncio
async def test_traduce_cada_anuncio_a_un_dispositivo_de_dominio() -> None:
    """De `BLEDevice` + `AdvertisementData` a `DiscoveredDevice`, y nada mas.

    Es el limite del transporte: si un objeto de Bleak sobreviviera a esta
    llamada, la capa de aplicacion acabaria dependiendo de Bleak.
    """
    scanner = BleDeviceScanner(discover=returning(found(("AA:BB:CC:DD:EE:FF", "ELK-BLEDOM", -63))))

    result = await scanner.scan(timeout_s=5.0)

    assert list(result) == [
        DiscoveredDevice(name="ELK-BLEDOM", address="AA:BB:CC:DD:EE:FF", rssi=-63)
    ]


@pytest.mark.asyncio
async def test_el_rssi_se_lee_del_anuncio_y_no_del_dispositivo() -> None:
    """En Bleak 3 `BLEDevice` ya no tiene `rssi`: esta en `AdvertisementData`.

    Los tutoriales de la 0.2x dicen lo contrario, y leerlo del sitio equivocado
    dejaria la lista sin ordenar y sin la unica pista de cercania que hay.
    """
    device = BLEDevice("AA:BB:CC:DD:EE:FF", "ELK-BLEDOM", None)
    assert not hasattr(device, "rssi")

    scanner = BleDeviceScanner(
        discover=returning({"AA:BB:CC:DD:EE:FF": (device, advertisement(rssi=-41))})
    )

    assert (await scanner.scan(timeout_s=1.0))[0].rssi == -41


@pytest.mark.asyncio
async def test_un_anuncio_sin_nombre_se_devuelve_con_nombre_nulo() -> None:
    """Muchos controladores de esta clase se anuncian sin nombre.

    Descartarlos seria esconder justo el dispositivo que se busca; devolver la
    cadena vacia obligaria a la UI a distinguir dos formas de "sin nombre".
    """
    scanner = BleDeviceScanner(discover=returning(found(("AA:BB:CC:DD:EE:FF", None, -80))))

    assert (await scanner.scan(timeout_s=1.0))[0].name is None


@pytest.mark.asyncio
async def test_el_nombre_local_del_anuncio_es_el_respaldo() -> None:
    """En algunas plataformas `BLEDevice.name` llega vacio y el anuncio si lo trae."""
    scanner = BleDeviceScanner(
        discover=returning(
            {
                "AA:BB:CC:DD:EE:FF": (
                    BLEDevice("AA:BB:CC:DD:EE:FF", None, None),
                    advertisement(rssi=-55, local_name="LEDBLE-1A2B3C"),
                )
            }
        )
    )

    assert (await scanner.scan(timeout_s=1.0))[0].name == "LEDBLE-1A2B3C"


@pytest.mark.asyncio
async def test_el_relleno_del_nombre_anunciado_se_recorta() -> None:
    """Caso real: el controlador de este proyecto se anuncia con espacios al final.

    Verificado con `tools/ble/scan.py` sobre el hardware: `'ELK-BLEDDM    '`.
    `DeviceService.register` usa este nombre como valor por defecto del
    dispositivo, asi que sin recortarlo el relleno acabaria persistido.
    """
    scanner = BleDeviceScanner(
        discover=returning(found(("BE:FF:00:11:22:33", "ELK-BLEDDM    ", -67)))
    )

    discovered = (await scanner.scan(timeout_s=1.0))[0]

    assert discovered.name == "ELK-BLEDDM"
    assert discovered.address == "BE:FF:00:11:22:33"


@pytest.mark.asyncio
async def test_el_filtro_no_exige_igualdad_exacta_con_el_nombre_configurado() -> None:
    """El nombre por defecto del proyecto (`ELK-BLEDOM`) no es el del hardware.

    El real tiene dos D (`ELK-BLEDDM`). Un filtro por igualdad habria dejado al
    usuario sin encontrar su propia tira; por eso se compara por subcadena, y por
    eso el filtro esta apagado de serie.
    """
    anuncios = found(("BE:FF:00:11:22:33", "ELK-BLEDDM    ", -67))

    exacto = BleDeviceScanner(name_filter="ELK-BLEDOM", discover=returning(anuncios))
    parcial = BleDeviceScanner(name_filter="  elk-bled  ", discover=returning(anuncios))

    assert await exacto.scan(timeout_s=1.0) == []
    assert len(await parcial.scan(timeout_s=1.0)) == 1


@pytest.mark.asyncio
async def test_el_timeout_pedido_llega_intacto_al_escaner() -> None:
    """Quien para la radio es Bleak: recortarlo aqui daria dos cotas para lo mismo."""
    recibidos: list[float] = []

    async def discover(timeout_s: float) -> Advertisements:
        recibidos.append(timeout_s)
        return {}

    await BleDeviceScanner(discover=discover).scan(timeout_s=7.5)

    assert recibidos == [7.5]


@pytest.mark.asyncio
async def test_devuelve_lo_mas_cercano_primero_y_con_orden_estable() -> None:
    """La señal mas fuerte primero: es el orden en el que se reconoce la tira propia."""
    scanner = BleDeviceScanner(
        discover=returning(
            found(
                ("11:11:11:11:11:11", "lejos", -90),
                ("22:22:22:22:22:22", "cerca", -40),
                ("33:33:33:33:33:33", "media", -70),
            )
        )
    )

    result = await scanner.scan(timeout_s=1.0)

    assert [device.address for device in result] == [
        "22:22:22:22:22:22",
        "33:33:33:33:33:33",
        "11:11:11:11:11:11",
    ]


@pytest.mark.asyncio
async def test_sin_filtro_se_devuelve_todo_lo_que_haya_cerca() -> None:
    """Por defecto NO se filtra por `LED_ROOM_DEVICE_NAME`.

    Filtrar de serie esconderia la tira: esta clase de controlador se anuncia
    como ELK-BLEDOM, ELK-BLEDOB, MELK-..., LEDBLE-... o sin nombre.
    """
    scanner = BleDeviceScanner(
        discover=returning(
            found(
                ("11:11:11:11:11:11", "ELK-BLEDOM", -50),
                ("22:22:22:22:22:22", "Mi Band 5", -60),
                ("33:33:33:33:33:33", None, -70),
            )
        )
    )

    assert len(await scanner.scan(timeout_s=1.0)) == 3


@pytest.mark.asyncio
async def test_el_filtro_por_nombre_es_opcional_y_no_distingue_mayusculas() -> None:
    """Se enciende cuando ya se sabe como se llama y el vecindario estorba."""
    scanner = BleDeviceScanner(
        name_filter="elk-bledom",
        discover=returning(
            found(
                ("11:11:11:11:11:11", "ELK-BLEDOM", -50),
                ("22:22:22:22:22:22", "Mi Band 5", -60),
                ("33:33:33:33:33:33", None, -70),
            )
        ),
    )

    result = await scanner.scan(timeout_s=1.0)

    assert [device.address for device in result] == ["11:11:11:11:11:11"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "fragmento"),
    [
        (BleakBluetoothNotAvailableReason.POWERED_OFF, "apagado"),
        (BleakBluetoothNotAvailableReason.NO_BLUETOOTH, "ningun adaptador"),
        (BleakBluetoothNotAvailableReason.DENIED_BY_SYSTEM, "denego"),
        (BleakBluetoothNotAvailableReason.UNKNOWN, "no esta disponible"),
    ],
    ids=["apagado", "sin-adaptador", "denegado", "desconocido"],
)
async def test_sin_radio_se_explica_la_causa_sin_filtrar_el_error_de_bleak(
    reason: BleakBluetoothNotAvailableReason, fragmento: str
) -> None:
    """Causa accionable, y un tipo de error propio que la frontera traduce a 503.

    En Windows, Bleak levanta `BleakBluetoothNotAvailableError` al arrancar el
    watcher: sin adaptador, sin rol central o con la radio apagada. El texto que
    viaja al cliente lo escribe el proyecto: el de Bleak puede llevar rutas de
    D-Bus o la direccion del controlador.
    """

    async def discover(timeout_s: float) -> Advertisements:
        raise BleakBluetoothNotAvailableError("D-Bus /org/bluez/hci0 dijo que no", reason)

    with pytest.raises(DeviceUnavailableError) as raised:
        await BleDeviceScanner(discover=discover).scan(timeout_s=1.0)

    assert fragmento in str(raised.value)
    assert "D-Bus" not in str(raised.value)


@pytest.mark.asyncio
async def test_un_fallo_del_escaneo_con_radio_presente_sigue_siendo_device_error() -> None:
    """No todo fallo es "no hay radio": esto es 502, no 503."""

    async def discover(timeout_s: float) -> Advertisements:
        raise BleakError("WinRT: 0x80070490 element not found")

    with pytest.raises(DeviceError) as raised:
        await BleDeviceScanner(discover=discover).scan(timeout_s=1.0)

    assert not isinstance(raised.value, DeviceUnavailableError)
    assert "0x80070490" not in str(raised.value)


@pytest.mark.asyncio
async def test_sin_socket_de_dbus_es_indisponibilidad_no_un_fallo_interno() -> None:
    """El caso de un contenedor sin la radio del anfitrion.

    `dbus_fast` sube un `FileNotFoundError` crudo, que no hereda de
    `BleakError`. Sin traducirlo, la API responde 500 `internal_error` y culpa
    al servidor de algo que es del entorno: la respuesta honesta es 503.
    """

    async def discover(timeout_s: float) -> Advertisements:
        raise FileNotFoundError(2, "No such file or directory", "/run/dbus/system_bus_socket")

    with pytest.raises(DeviceUnavailableError) as raised:
        await BleDeviceScanner(discover=discover).scan(timeout_s=1.0)

    # La ruta del socket es un detalle interno: no viaja al cliente.
    assert "system_bus_socket" not in str(raised.value)


@pytest.mark.asyncio
async def test_el_escaneo_es_cancelable() -> None:
    """Un escaneo colgado no puede retener el turno unico de `GET /devices/scan`.

    `CancelledError` hereda de `BaseException`, asi que ninguna rama de
    traduccion lo captura y sube intacto; lo que se comprueba aqui es que ese
    razonamiento sigue siendo cierto y que el escaneo subyacente se cancela.
    """
    empezado = asyncio.Event()
    cancelado = False

    async def discover(timeout_s: float) -> Advertisements:
        nonlocal cancelado
        empezado.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelado = True
            raise
        return {}

    tarea = asyncio.create_task(BleDeviceScanner(discover=discover).scan(timeout_s=3600))
    await empezado.wait()
    tarea.cancel()

    with pytest.raises(asyncio.CancelledError):
        await tarea
    assert cancelado


@pytest.mark.asyncio
async def test_no_ver_nada_no_es_un_error() -> None:
    """Una lista vacia es una respuesta correcta: 200 [], no una excepcion."""
    assert await BleDeviceScanner(discover=returning({})).scan(timeout_s=1.0) == []
