"""Tabla de adaptadores: que se construye para cada `DeviceType`.

Una cadena de `if/elif` compila igual, pero nada obliga a que **todo** miembro
de `DeviceType` tenga constructor: el dia que se añada `WLED`, el fallo aparece
en tiempo de ejecucion y solo con esa configuracion puesta. Con una tabla
explicita, un test recorre el enum y rompe la build (NEXT_STEPS A2).

Diccionario explicito a proposito: **nada de entry points ni de descubrimiento
por plugins**. Con dos adaptadores, la extensibilidad dinamica costaria errores
de importacion diferidos y haria imposible comprobar la cobertura del enum, que
es justo la garantia que se busca aqui.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from backend.app.config import Settings
from backend.app.domain.devices.models import DeviceType
from backend.app.domain.devices.ports import DeviceDiscoveryPort, LightDevicePort
from backend.app.infrastructure.devices.null_adapter import NullLightDeviceAdapter
from backend.app.infrastructure.devices.null_discovery import NullDiscoveryAdapter

#: Un adaptador se construye a partir de la configuracion y de nada mas: sin
#: estado global, sin leer el entorno por su cuenta.
LightDeviceFactory = Callable[[Settings], LightDevicePort]
DeviceDiscoveryFactory = Callable[[Settings], DeviceDiscoveryPort]


@dataclass(frozen=True, slots=True)
class AdapterRegistration:
    """Todo lo que hay que aportar para dar de alta una familia de hardware.

    Los dos puertos van juntos en una sola entrada, y no en dos mapas
    paralelos, para que dar de alta un adaptador sea una unica entrada y un
    unico archivo: con dos mapas se puede registrar el control y olvidar el
    descubrimiento, y haria falta un segundo test de cobertura para detectarlo.

    **Juntos no es acoplados**: son dos campos, se construyen por separado y
    `factory.build_device_discovery` nunca toca `light_device`. Eso permitio que
    `lotus_lantern` tuviera escaner BLE real mientras su control seguia sin
    implementar, y es lo que permitira a la siguiente familia ir a su ritmo.
    """

    light_device: LightDeviceFactory
    discovery: DeviceDiscoveryFactory

    #: Si esta familia de hardware puede encontrar dispositivos por si misma.
    #:
    #: Es un dato del adaptador y se declara **aqui**, junto a sus dos
    #: constructores, en vez de resolverse con un `if device_type is NULL`
    #: repartido por la API: ese `if` habria que recordarlo en cada sitio que
    #: pregunte, y nada obligaria a revisarlo al añadir una familia nueva.
    #:
    #: **Sin valor por defecto a proposito.** Es lo que convierte "declarar la
    #: capacidad" en obligatorio: dar de alta un adaptador nuevo sin decir si
    #: descubre no compila (mypy) y no construye (`TypeError`).
    #:
    #: Describe la *familia*, no el estado del enlace: quien tiene radio la
    #: sigue teniendo aunque su adaptador de control no exista todavia. "Esta
    #: familia descubre" y "el enlace funciona ahora" son preguntas distintas, y
    #: la segunda la responde `GET /api/v1/state` con `connected` y `last_error`.
    supports_discovery: bool


def _build_null_light_device(settings: Settings) -> LightDevicePort:
    return NullLightDeviceAdapter()


def _build_null_discovery(settings: Settings) -> DeviceDiscoveryPort:
    return NullDiscoveryAdapter()


def _lotus_lantern_light_device(settings: Settings) -> LightDevicePort:
    """Control real por BLE, con el protocolo verificado en la Fase 0.

    Las tramas estan probadas contra el hardware y documentadas en
    `docs/BLE_PROTOCOL.md`; `infrastructure/bluetooth/protocol.py` es el unico
    sitio donde viven.

    **El import es diferido**, por la misma razon que en el descubrimiento:
    `bleak` solo puede aparecer bajo `infrastructure/bluetooth/`, y construir el
    adaptador sin hardware no debe cargar Bleak en la CI ni en un host sin
    radio.
    """
    from backend.app.infrastructure.bluetooth.lotus_lantern import LotusLanternBLEAdapter

    return LotusLanternBLEAdapter(connect_timeout_s=settings.ble_connect_timeout)


def _lotus_lantern_discovery(settings: Settings) -> DeviceDiscoveryPort:
    """Escaneo BLE real. **Descubrir no es controlar.**

    Este constructor si funciona hoy, a diferencia del de control de arriba:
    leer anuncios BLE no necesita ningun UUID ni ningun byte de comando, asi que
    no depende de la Fase 0 -- es lo que la desbloquea, porque sin la direccion
    real de la tira no hay nada contra lo que volcar el arbol GATT.

    **El import es diferido a proposito.** `bleak` solo puede aparecer bajo
    `infrastructure/bluetooth/` (lo comprueba un test), y ademas la factoria de
    dispositivos tiene que seguir siendo importable donde no haga falta: con el
    import arriba, cualquier host y la CI cargarian Bleak solo por construir el
    adaptador sin hardware.
    """
    from backend.app.infrastructure.bluetooth.scanner import BleDeviceScanner

    return BleDeviceScanner(name_filter=settings.scan_name_filter)


#: Fuente unica de la relacion tipo de dispositivo -> implementaciones.
ADAPTERS: Final[Mapping[DeviceType, AdapterRegistration]] = {
    DeviceType.NULL: AdapterRegistration(
        light_device=_build_null_light_device,
        discovery=_build_null_discovery,
        # No hay radio: `NullDiscoveryAdapter` devuelve siempre la lista vacia.
        # Declararlo permite al cliente no ofrecer siquiera el boton de buscar,
        # en vez de tener que adivinar que significa un `200 []`.
        supports_discovery=False,
    ),
    DeviceType.LOTUS_LANTERN: AdapterRegistration(
        light_device=_lotus_lantern_light_device,
        discovery=_lotus_lantern_discovery,
        # BLE: descubrir es la unica forma de llegar a este hardware.
        supports_discovery=True,
    ),
}
