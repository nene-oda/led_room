"""Adaptador de control del controlador LotusLantern / ELK-BLEDOM sobre BLE.

Implementa `LightDevicePort` traduciendo cada operacion a la trama verificada
que corresponde (`protocol.py`) y escribiendola en el enlace. No decide ninguna
trama por su cuenta: **toda la codificacion vive en `protocol`**, para que
exista un unico sitio donde cambiar el protocolo si el hardware cambia.

Lo que este modulo NO hace, a proposito:

* **No serializa las escrituras.** `SerializedLightDevice` lo hace por
  composicion en la factoria, asi que ningun adaptador debe traer su propio
  `Lock` (`devices/serialized.py`).
* **No limita la frecuencia.** El *throttling* es politica de producto y vive en
  la capa de aplicacion.
* **No reintenta ni reconecta solo.** Un reintento callado aqui competiria con
  el `connect()` que pida el usuario y produciria dos enlaces en vuelo sobre un
  controlador que solo admite uno.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from bleak import BleakClient
from bleak.exc import BleakBluetoothNotAvailableError, BleakDeviceNotFoundError, BleakError

from backend.app.domain.devices.models import (
    SINGLE_COLOR_STRIP,
    DeviceCapabilities,
    DeviceTarget,
)
from backend.app.domain.devices.ports import (
    DeviceError,
    DeviceNotConnectedError,
    DeviceUnavailableError,
)
from backend.app.infrastructure.bluetooth import protocol
from backend.app.infrastructure.devices.base import BaseLightDevice

logger = logging.getLogger(__name__)


class BleClient(Protocol):
    """Lo unico que este adaptador necesita de un cliente BLE.

    Es un puerto minimo, no la superficie entera de `BleakClient`: permite
    probar el adaptador **sin radio** y evita que los tests tengan que imitar
    metodos que no se usan.
    """

    @property
    def is_connected(self) -> bool: ...

    async def connect(self, **kwargs: Any) -> None: ...

    async def disconnect(self) -> None: ...

    async def write_gatt_char(
        self, char_specifier: str, data: bytes, response: bool | None = None
    ) -> None: ...


class ClientFactory(Protocol):
    """Como se crea un cliente para una direccion. Se inyecta para poder probar."""

    def __call__(self, address: str, timeout_s: float) -> BleClient: ...


def _default_client(address: str, timeout_s: float) -> BleClient:
    """Cliente real de Bleak. `timeout` cubre la busqueda previa a la conexion."""
    return BleakClient(address, timeout=timeout_s)


class LotusLanternBLEAdapter(BaseLightDevice):
    """Control real de la tira por BLE.

    Las capacidades por defecto son las de una tira de un solo color
    (`SINGLE_COLOR_STRIP`): este controlador ilumina toda la tira del mismo
    color, no es direccionable, y decir lo contrario haria que el motor de
    efectos prometiera degradados espaciales que el hardware no puede dar.
    """

    def __init__(
        self,
        *,
        connect_timeout_s: float,
        client_factory: ClientFactory = _default_client,
        capabilities: DeviceCapabilities | None = None,
    ) -> None:
        super().__init__(capabilities or SINGLE_COLOR_STRIP)
        self._connect_timeout_s = connect_timeout_s
        self._client_factory = client_factory
        self._client: BleClient | None = None
        self._address: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def address(self) -> str | None:
        """Direccion del enlace abierto, o `None`. Inspeccionable en los tests."""
        return self._address

    async def connect(self, target: DeviceTarget) -> None:
        """Abre el enlace. Idempotente sobre el mismo destino.

        Reconectar al mismo destino con el enlace ya abierto no hace nada: el
        contrato del puerto lo exige, y ademas este controlador **solo admite
        una conexion**, asi que un segundo enlace no fallaria limpiamente sino
        que dejaria fuera al primero.

        Conectar a un destino **distinto** cierra el anterior primero. Un
        adaptador controla un dispositivo a la vez; dejar el enlace viejo
        abierto retendria la tira anterior sin que nadie la gobierne.
        """
        if self.is_connected and self._address == target.address:
            logger.debug("Enlace ya abierto con %s: no se reabre", target.address)
            return

        if self._client is not None:
            await self.disconnect()

        client = self._client_factory(target.address, self._connect_timeout_s)
        try:
            await client.connect()
        except BleakBluetoothNotAvailableError as error:
            raise DeviceUnavailableError(_NO_RADIO) from error
        except BleakDeviceNotFoundError as error:
            raise DeviceError(_NOT_FOUND.format(address=target.address)) from error
        except BleakError as error:
            logger.warning("Fallo al conectar con %s: %s", target.address, error)
            raise DeviceError(_CONNECT_FAILED) from error
        except OSError as error:
            # Mismo caso que en el escaner: sin socket de D-Bus, `dbus_fast`
            # sube un `FileNotFoundError` crudo que no hereda de `BleakError`.
            logger.warning("Sin acceso al servicio Bluetooth del sistema: %s", error)
            raise DeviceUnavailableError(_NO_BLUETOOTH_SERVICE) from error

        self._client = client
        self._address = target.address
        logger.info("Enlace BLE abierto con %s", target.address)

    async def disconnect(self) -> None:
        """Cierra el enlace. Seguro de llamar repetidamente y sin enlace.

        El estado local se limpia **pase lo que pase**: si un fallo al cerrar
        dejara el adaptador creyendose conectado, ya no habria forma de volver a
        conectar, porque `connect()` es idempotente sobre el mismo destino.
        """
        client, address = self._client, self._address
        self._client = None
        self._address = None
        if client is None:
            return
        try:
            await client.disconnect()
        except (BleakError, OSError) as error:
            # Se registra y se sigue: el enlace se da por perdido igualmente, y
            # propagar impediria conectar de nuevo.
            logger.warning("Fallo al cerrar el enlace con %s: %s", address, error)
        else:
            logger.info("Enlace BLE cerrado con %s", address)

    async def set_power(self, value: bool) -> None:
        """Enciende o apaga.

        Encender no reenvia color ni brillo: el controlador los conserva y
        vuelve con los que tenia (verificado, `docs/BLE_PROTOCOL.md` 3).
        """
        await self._write(protocol.encode_power(value))

    async def set_color(self, red: int, green: int, blue: int) -> None:
        self._validate_color(red, green, blue)
        await self._write(protocol.encode_color(red, green, blue))

    async def set_brightness(self, brightness: int) -> None:
        self._validate_brightness(brightness)
        await self._write(protocol.encode_brightness(brightness))

    async def _write(self, frame: bytes) -> None:
        """Envia una trama ya codificada.

        `response=False` no es una preferencia: la caracteristica `fff3` declara
        `write-without-response` y **no** admite escritura con respuesta, asi
        que pedir confirmacion falla.

        La contrapartida es que una escritura aceptada no demuestra que el
        controlador haya hecho nada: no hay acuse. Por eso el estado del
        hardware se sigue tratando como potencialmente divergente del deseado.
        """
        client = self._client
        if client is None or not client.is_connected:
            raise DeviceNotConnectedError(_NOT_CONNECTED)
        try:
            await client.write_gatt_char(protocol.WRITE_CHARACTERISTIC_UUID, frame, response=False)
        except BleakError as error:
            logger.warning("Fallo la escritura BLE en %s: %s", self._address, error)
            raise DeviceError(_WRITE_FAILED) from error
        except OSError as error:
            logger.warning("Se perdio el transporte al escribir: %s", error)
            raise DeviceUnavailableError(_NO_BLUETOOTH_SERVICE) from error


#: Mensajes de cara al usuario. Los escribe el proyecto y no se toma el `str()`
#: de una excepcion de Bleak: puede llevar rutas de D-Bus o la direccion del
#: controlador, y la politica de errores prohibe devolver eso.
_NO_RADIO = "El Bluetooth de este equipo no esta disponible."
_NO_BLUETOOTH_SERVICE = (
    "Este servicio no alcanza el Bluetooth del sistema. Si corre en un "
    "contenedor, necesita acceso a la radio del anfitrion."
)
_NOT_FOUND = (
    "No se encontro el dispositivo {address}. Comprueba que esta enchufado, "
    "cerca, y que ninguna otra aplicacion lo tiene conectado."
)
_CONNECT_FAILED = "No se pudo abrir el enlace con el dispositivo."
_NOT_CONNECTED = "No hay ningun dispositivo conectado."
_WRITE_FAILED = "Se perdio el enlace con el dispositivo."
