"""DTO de `GET /system`: que puede hacer ESTE servidor, no que hay en la habitacion.

Es deliberadamente estatico -- se decide al arrancar y no cambia mientras el
proceso vive -- y por eso no viaja en `GlobalStateRead` ni en el frame
`state.snapshot`: ese cuerpo describe lo mutable (enlace, luz, efecto, escena),
lleva `version` y se difunde en cada cambio. Meter aqui la eleccion de adaptador
haria que cada arrastre del selector de color reenviara una configuracion que no
puede haber cambiado.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.domain.devices.models import DeviceType


class SystemInfoRead(BaseModel):
    """Capacidades del servidor, para que el cliente no tenga que adivinarlas.

    Existe por un fallo de producto concreto: con el adaptador sin hardware,
    `GET /devices/scan` responde `200 []` **al instante**, y eso es ambiguo --
    "busque y no habia nada" y "este servidor no tiene radio y nunca encontrara
    nada" se ven exactamente igual. La UI se veia obligada a enumerar las dos
    posibilidades *despues* de escanear. Con esto puede decidirlo **antes**.
    """

    #: El `DeviceType` activo (`LED_ROOM_DEVICE_ADAPTER`). Se reutiliza el enum
    #: de dominio en vez de un `Literal` propio: el vocabulario de adaptador es
    #: uno solo en todo el proyecto (ARCHITECTURE 3.7).
    adapter_type: DeviceType

    #: Familia cuyo escaner esta activo (`LED_ROOM_DEVICE_DISCOVERY`, y si no se
    #: define, la misma que `adapter_type`).
    #:
    #: Es un campo aparte porque descubrir y controlar son puertos distintos y
    #: pueden ir a distinto ritmo: hoy lo normal es controlar con `null` -- sin
    #: hardware -- y descubrir con `lotus_lantern` -- radio BLE real --. Sin
    #: esto, `supports_discovery: true` junto a `adapter_type: "null"` parecia
    #: una contradiccion y no habia forma de saber que escaner respondio.
    discovery_type: DeviceType

    #: Si este servidor puede encontrar hardware. Lo declara `AdapterRegistration`
    #: de `discovery_type`; aqui solo se transporta.
    supports_discovery: bool

    #: Cota superior de `GET /devices/scan` (`LED_ROOM_BLE_SCAN_TIMEOUT`). El
    #: cliente puede pedir menos, nunca mas, asi que es lo que necesita para
    #: dibujar una barra de progreso que signifique algo.
    #:
    #: Segundos y en punto flotante, como el ajuste: redondear a entero mentiria
    #: sobre un `LED_ROOM_BLE_SCAN_TIMEOUT=2.5`.
    scan_timeout_seconds: float = Field(gt=0)
