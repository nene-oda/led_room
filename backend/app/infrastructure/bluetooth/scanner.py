"""Descubrimiento BLE real sobre `BleakScanner` (NEXT_STEPS 4.1, Fase 0).

**Por que esto puede existir antes de la Fase 0 y el adaptador de control no.**
Escanear solo lee anuncios BLE: no hace falta ningun UUID de servicio, ninguna
caracteristica ni ningun byte de comando. La regla de ARCHITECTURE 8 -- no
inventar protocolo -- protege a `set_power`, `set_color` y `set_brightness`, que
escriben en el hardware. Este modulo no escribe nada, y es justamente lo que
desbloquea la Fase 0: sin la direccion real de la tira no hay nada contra lo que
ejecutar `tools/ble/gatt_dump.py`.

Nada de `bleak` sale de aqui: la unica salida son `DiscoveredDevice` del dominio
y las excepciones de dominio de `domain/devices/ports.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Final

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import (
    BleakBluetoothNotAvailableError,
    BleakBluetoothNotAvailableReason,
    BleakError,
)

from backend.app.domain.devices.models import DiscoveredDevice
from backend.app.domain.devices.ports import DeviceError, DeviceUnavailableError

logger = logging.getLogger(__name__)

#: Lo que devuelve `BleakScanner.discover(return_adv=True)` en Bleak 3.x.
#: El RSSI vive en `AdvertisementData`, no en `BLEDevice`: en Bleak 3 el
#: `BLEDevice.rssi` de los tutoriales de la 0.2x ya no existe.
Advertisements = Mapping[str, tuple[BLEDevice, AdvertisementData]]

#: Se inyecta para poder probar este adaptador sin radio. Toma los segundos de
#: escaneo y nada mas: un `Protocol` con la firma completa de
#: `BleakScanner.discover` obligaria a los tests a imitar sus sobrecargas.
ScanFunction = Callable[[float], Awaitable[Advertisements]]

#: Que hacer con cada motivo por el que Bleak dice que no hay Bluetooth. El
#: texto viaja al cliente, asi que lo escribe el proyecto: el `str()` de una
#: excepcion de Bleak puede llevar rutas de D-Bus o la direccion del
#: controlador, y la politica de errores prohibe devolver eso.
_UNAVAILABLE_MESSAGES: Final[Mapping[BleakBluetoothNotAvailableReason, str]] = {
    BleakBluetoothNotAvailableReason.NO_BLUETOOTH: (
        "Este equipo no tiene ningun adaptador Bluetooth disponible."
    ),
    BleakBluetoothNotAvailableReason.NO_BLE_CENTRAL_ROLE: (
        "El adaptador Bluetooth de este equipo no admite el rol central de BLE, "
        "necesario para buscar dispositivos."
    ),
    BleakBluetoothNotAvailableReason.POWERED_OFF: (
        "El Bluetooth de este equipo esta apagado: enciendelo y vuelve a buscar."
    ),
    BleakBluetoothNotAvailableReason.DENIED_BY_USER: (
        "El sistema denego el permiso de Bluetooth a este servicio."
    ),
    BleakBluetoothNotAvailableReason.DENIED_BY_SYSTEM: (
        "El sistema denego el acceso al Bluetooth a este servicio."
    ),
}

#: Para `DENIED_BY_UNKNOWN`, `UNKNOWN` y cualquier motivo que añada Bleak.
_UNAVAILABLE_FALLBACK: Final = "El Bluetooth de este equipo no esta disponible."

#: Fallo del escaneo con radio presente (el enlace se cayo a mitad, el backend
#: del sistema devolvio un error). No se publica el texto de Bleak.
_SCAN_FAILED: Final = "El adaptador Bluetooth de este equipo no pudo completar la busqueda."

#: El servicio Bluetooth del sistema no esta al alcance: no hay socket de D-Bus
#: (contenedor sin la radio del anfitrion) o `bluetoothd` no esta corriendo. Es
#: indisponibilidad del entorno, no un fallo del escaneo.
_NO_BLUETOOTH_SERVICE: Final = (
    "Este servicio no alcanza el Bluetooth del sistema. Si corre en un "
    "contenedor, necesita acceso a la radio del anfitrion."
)


async def discover_advertisements(timeout_s: float) -> Advertisements:
    """`ScanFunction` por defecto: el escaneo real de Bleak."""
    return await BleakScanner.discover(timeout=timeout_s, return_adv=True)


class BleDeviceScanner:
    """Implementa `DeviceDiscoveryPort` leyendo anuncios BLE.

    **No filtra por nombre por defecto, y es deliberado.** Los controladores de
    esta clase se anuncian como `ELK-BLEDOM`, `ELK-BLEDOB`, `MELK-...`,
    `LEDBLE-...` o directamente sin nombre, asi que filtrar por
    `LED_ROOM_DEVICE_NAME` de serie esconderia la tira que se intenta encontrar.
    El filtro existe para *despues*, cuando ya se sabe como se llama y el ruido
    del vecindario estorba; se activa con `LED_ROOM_BLE_SCAN_NAME_FILTER`.
    """

    def __init__(
        self,
        *,
        name_filter: str | None = None,
        discover: ScanFunction = discover_advertisements,
    ) -> None:
        normalized = (name_filter or "").strip().casefold()
        self._name_filter: str | None = normalized or None
        self._discover = discover

    async def scan(self, timeout_s: float) -> Sequence[DiscoveredDevice]:
        """Devuelve lo anunciado durante `timeout_s` segundos.

        El timeout se le pasa entero a Bleak, que es quien para la radio: no se
        envuelve en un `wait_for` propio porque `DeviceService.scan` ya pone la
        red de seguridad (`SCAN_GRACE_S`) y dos cotas para lo mismo solo
        consiguen que nadie sepa cual expiro.

        Es cancelable sin nada que deshacer: `CancelledError` no lo captura
        ninguna de las ramas de abajo, asi que sube intacto y Bleak cierra su
        propio escaner al desenrollarse.
        """
        try:
            found = await self._discover(timeout_s)
        except BleakBluetoothNotAvailableError as error:
            logger.warning("Bluetooth no disponible (%s): %s", error.reason.name, error)
            raise DeviceUnavailableError(_explain_unavailable(error)) from error
        except BleakError as error:
            logger.warning("Fallo el escaneo BLE: %s", error)
            raise DeviceError(_SCAN_FAILED) from error
        except OSError as error:
            # Sin socket de D-Bus, `dbus_fast` sube un `FileNotFoundError`
            # crudo, que no hereda de `BleakError`. Sin esta rama sale un 500
            # `internal_error`, cuando lo cierto es que el entorno no tiene
            # radio al alcance: es exactamente lo que ve quien pide
            # descubrimiento BLE dentro de Docker Desktop.
            logger.warning("Sin acceso al servicio Bluetooth del sistema: %s", error)
            raise DeviceUnavailableError(_NO_BLUETOOTH_SERVICE) from error

        discovered = [
            _to_domain(address, device, advertisement)
            for address, (device, advertisement) in found.items()
        ]
        visible = [device for device in discovered if self._accepts(device.name)]

        logger.info(
            "Escaneo BLE de %.1fs: %d anuncio(s), %d visible(s)",
            timeout_s,
            len(discovered),
            len(visible),
        )
        # Mas cerca primero: es el orden en el que una persona reconoce su tira.
        # La direccion desempata para que dos escaneos iguales den el mismo orden.
        return sorted(visible, key=_proximity)

    def _accepts(self, name: str | None) -> bool:
        """Coincidencia por SUBCADENA y sin distinguir mayusculas.

        No por igualdad: el nombre real llego como `'ELK-BLEDDM    '` -- dos D y
        con relleno --, asi que un `==` contra el valor por defecto del proyecto
        (`ELK-BLEDOM`) habria escondido la tira que se estaba buscando. El
        recorte ya lo hizo `_to_domain`; comparar por subcadena ademas tolera
        prefijos y sufijos de modelo (`MELK-...`, `LEDBLE-...`).
        """
        if self._name_filter is None:
            return True
        return name is not None and self._name_filter in name.casefold()


def _proximity(device: DiscoveredDevice) -> tuple[int, str]:
    """Clave de orden: senal mas fuerte primero, y sin RSSI al final.

    `None` no se colapsa con "muy lejos" usando un `or`: un RSSI de 0 es un
    entero valido y `0 or -127` lo mandaria al fondo de la lista.
    """
    rssi = device.rssi
    return (127 if rssi is None else -rssi, device.address)


def _to_domain(
    address: str,
    device: BLEDevice,
    advertisement: AdvertisementData,
) -> DiscoveredDevice:
    """Traduce un anuncio a dominio. Aqui muere `bleak`.

    `local_name` es el respaldo del nombre porque en algunas plataformas
    `BLEDevice.name` llega vacio aunque el anuncio si lo traiga; una cadena vacia
    se normaliza a `None`, que es lo que el dominio usa para "sin nombre".

    **El nombre se recorta**, y no es cosmetica: el controlador de este proyecto
    se anuncia literalmente como `'ELK-BLEDDM    '`, con relleno al final
    (verificado con `tools/ble/scan.py` sobre el hardware real). Ese nombre es el
    que `DeviceService.register` usa por defecto para el `Device`, asi que sin
    recortarlo el relleno acabaria en la base de datos y en la UI. La direccion
    NO se toca: es la identidad y se guarda tal cual la da la plataforma.
    """
    name = (device.name or advertisement.local_name or "").strip()
    return DiscoveredDevice(
        name=name or None,
        address=device.address or address,
        rssi=advertisement.rssi,
    )


def _explain_unavailable(error: BleakBluetoothNotAvailableError) -> str:
    return _UNAVAILABLE_MESSAGES.get(error.reason, _UNAVAILABLE_FALLBACK)
