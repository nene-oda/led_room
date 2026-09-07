"""Seleccion de las implementaciones de dispositivo segun la configuracion.

Este modulo es el unico que conoce a la vez los puertos y sus implementaciones.
El dominio y la capa de aplicacion solo ven `LightDevicePort` y
`DeviceDiscoveryPort`.

La eleccion vive en `registry.ADAPTERS`; aqui solo queda la busqueda, la
composicion del escritor serializado y un error de configuracion legible.
"""

from __future__ import annotations

from backend.app.config import Settings
from backend.app.domain.devices.models import DeviceType
from backend.app.domain.devices.ports import DeviceDiscoveryPort, LightDevicePort
from backend.app.infrastructure.devices import registry
from backend.app.infrastructure.devices.serialized import SerializedLightDevice


def build_light_device(settings: Settings) -> LightDevicePort:
    """Construye el adaptador de `LED_ROOM_DEVICE_ADAPTER`, ya serializado.

    La serializacion se compone **aqui** y no en cada adaptador: asi todo
    adaptador presente y futuro obtiene el escritor unico sin repetir el
    `asyncio.Lock`, y nadie puede olvidarlo.
    """
    device = _registration(settings.device_adapter).light_device(settings)
    return SerializedLightDevice(device, write_timeout_s=settings.ble_write_timeout)


def build_device_discovery(settings: Settings) -> DeviceDiscoveryPort:
    """Construye el descubridor de `LED_ROOM_DEVICE_DISCOVERY`.

    Lo elige `Settings.discovery_adapter`, que por defecto es la misma familia
    que controla. Se puede separar porque descubrir y controlar son puertos
    distintos y hoy van a distinto ritmo: el escaner BLE ya es real y el
    adaptador de control sigue esperando al protocolo verificado.

    No se serializa: un escaneo no escribe en el dispositivo. Que un escaneo no
    se solape con otro es una decision de caso de uso (`409 ya en curso`,
    NEXT_STEPS 4.3), no una invariante del transporte.
    """
    return _registration(settings.discovery_adapter).discovery(settings)


def supports_discovery(settings: Settings) -> bool:
    """Si el adaptador configurado puede descubrir dispositivos por si mismo.

    Responde por la familia que DESCUBRE (`Settings.discovery_adapter`), no por
    la que controla: con `LED_ROOM_DEVICE_ADAPTER=null` y
    `LED_ROOM_DEVICE_DISCOVERY=lotus_lantern` este servidor si tiene radio, y
    decir que no seria mentirle al cliente que decide si ofrecer el boton.

    No construye nada: es la declaracion del registro, asi que responde tambien
    para una familia cuyo constructor todavia no existe. Se consulta al arrancar
    y viaja en `GET /api/v1/system` para que el cliente sepa **antes** de pulsar
    nada si este servidor puede encontrar hardware, en lugar de deducirlo de un
    `200 []` ambiguo.
    """
    return _registration(settings.discovery_adapter).supports_discovery


def _registration(device_type: DeviceType) -> registry.AdapterRegistration:
    try:
        return registry.ADAPTERS[device_type]
    except KeyError:
        known = ", ".join(sorted(str(key) for key in registry.ADAPTERS))
        raise ValueError(
            f"Adaptador de dispositivo sin constructor registrado: {device_type!r}. "
            f"Registrados: {known}."
        ) from None
