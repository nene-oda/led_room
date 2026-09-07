"""Casos de uso de dispositivos: descubrir, registrar, conectar y desconectar.

Cierra los dos huecos que dejo abierta la oleada 2B:

1. **Quien genera el `UUID`**: lo genera **el servidor**, aqui, con una factoria
   inyectada (`uuid4` por defecto). No lo genera el cliente, que no puede
   inventar la identidad de algo que acaba de descubrir; ni la base, que en
   SQLite no tiene un DEFAULT de UUID y obligaria a un round-trip para conocer
   el id recien creado. La factoria inyectada mantiene los tests deterministas.
   Y el id que vale es **el que devuelve el repositorio**: cuando la direccion
   ya estaba registrada, `upsert` conserva la fila existente y su `id`, para no
   dejar huerfanas las filas hijas.

2. **Que pasa con `ble_name`**: no se persiste desde aqui. El dominio no lo
   modela y el mapper lo preserva a proposito, asi que escribirlo exigiria un
   metodo nuevo en `DeviceRepository`. Lo que si se usa es el nombre anunciado
   en el escaneo como **valor por defecto** del nombre visible del dispositivo
   (`DiscoveredDevice.name` -> `Device.name`), y la direccion como ultimo
   recurso: muchos controladores de esta clase se anuncian sin nombre. Si algun
   dia hace falta el nombre crudo del anuncio para diagnostico, entra por el
   puerto de repositorio, no colandose por el mapper.

El repositorio se tipa contra el **Protocol de dominio**, nunca contra
`SQLModelDeviceRepository`: asi el servicio se prueba con un doble en memoria y
no queda atado a SQLModel.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from contextlib import suppress
from typing import Final
from uuid import UUID, uuid4

from backend.app.application.errors import (
    DeviceBusyError,
    DeviceNotFoundError,
    translate_error,
)
from backend.app.application.state_store import StateStore
from backend.app.domain.devices.models import (
    Device,
    DeviceStatus,
    DeviceTarget,
    DeviceType,
    DiscoveredDevice,
)
from backend.app.domain.devices.ports import (
    DeviceDiscoveryPort,
    DeviceError,
    LightDevicePort,
)
from backend.app.domain.devices.repositories import DeviceRepository
from backend.app.domain.events import DeviceConnected, DeviceDisconnected
from backend.app.domain.lighting import LightState

logger = logging.getLogger(__name__)

#: Margen sobre el timeout pedido al escaner. El puerto promete devolver lo
#: visto en `timeout_s`, pero cerrar la radio y traducir los resultados lleva su
#: tiempo; sin margen, un escaner que se cuelgue retendria la peticion HTTP para
#: siempre. Es una red de seguridad, no el timeout del escaneo.
SCAN_GRACE_S: Final = 1.0


class DeviceService:
    """Ciclo de vida del unico enlace de dispositivo del proceso.

    Es de vida corta: se construye por operacion con el repositorio de esa
    peticion (la `Session` de SQLModel no debe sobrevivir a la peticion que la
    abrio). Lo de larga vida (el adaptador y el store) se le inyecta ya
    construido.
    """

    def __init__(
        self,
        *,
        repository: DeviceRepository,
        discovery: DeviceDiscoveryPort,
        device: LightDevicePort,
        store: StateStore,
        adapter_type: DeviceType,
        scan_timeout_s: float,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._repository = repository
        self._discovery = discovery
        self._device = device
        self._store = store
        self._adapter_type = adapter_type
        self._scan_timeout_s = scan_timeout_s
        self._new_id = new_id

    def list_devices(self) -> Sequence[Device]:
        """Dispositivos utilizables. Metodo sincrono: solo lee el repositorio."""
        return self._repository.list_enabled()

    def get_device(self, device_id: UUID) -> Device:
        device = self._repository.get(device_id)
        if device is None:
            raise DeviceNotFoundError(f"No hay ningun dispositivo registrado con id {device_id}.")
        return device

    async def scan(self, timeout_s: float | None = None) -> Sequence[DiscoveredDevice]:
        """Escanea, siempre acotado por `LED_ROOM_BLE_SCAN_TIMEOUT`.

        Un cliente puede pedir menos tiempo, nunca mas: el limite del escaneo es
        una decision de despliegue, no del cliente.
        """
        timeout = (
            self._scan_timeout_s if timeout_s is None else min(timeout_s, self._scan_timeout_s)
        )
        if timeout <= 0:
            raise ValueError(f"El timeout de escaneo debe ser positivo; se recibio {timeout_s}")

        try:
            return await asyncio.wait_for(self._discovery.scan(timeout), timeout + SCAN_GRACE_S)
        except TimeoutError as error:
            # Traducido en la frontera: ninguna capa superior debe conocer
            # `asyncio.TimeoutError` (NEXT_STEPS A6).
            raise DeviceError(
                f"El escaneo de dispositivos no termino en {timeout + SCAN_GRACE_S:g} s."
            ) from error

    def register(self, discovered: DiscoveredDevice, *, name: str | None = None) -> Device:
        """Convierte un resultado de escaneo en un dispositivo con identidad.

        El `adapter_type` no es un parametro: el escaneo lo ha producido el
        descubridor de la familia configurada, asi que lo descubierto es de esa
        familia. Las capacidades salen del propio adaptador, que es quien las
        declara; no se inventan aqui.
        """
        existing = self._repository.get_by_address(discovered.address)
        if existing is not None:
            # Registrar dos veces el mismo controlador no crea otro dispositivo
            # ni cambia su id: como mucho lo renombra.
            renamed = existing.model_copy(update={"name": name or existing.name})
            return self._repository.upsert(renamed)

        return self._repository.upsert(
            Device(
                id=self._new_id(),
                name=name or discovered.name or discovered.address,
                adapter_type=self._adapter_type,
                address=discovered.address,
                capabilities=self._device.capabilities,
            )
        )

    async def connect(self, device_id: UUID) -> DeviceStatus:
        """Abre el enlace y reconcilia el hardware con el estado deseado.

        El hardware puede estar en cualquier estado: acaba de recibir corriente,
        o lo movio la app del movil. Reaplicar el ultimo estado deseado es la
        unica forma de que el store y la tira digan lo mismo justo despues de
        conectar.

        Las dos lecturas del repositorio que hay aqui (`get_device` y
        `load_state`) corren en el bucle de eventos, a diferencia de las de la
        frontera HTTP: sacarlas exigiria que esta capa importara Starlette, y eso
        invertiria la direccion de las dependencias. Se acepta porque son
        lecturas de una fila por clave primaria y no `commit()`, que es lo que
        puede quedarse esperando a `busy_timeout`.
        """
        device = self.get_device(device_id)
        await self._ensure_link_free(device.id)

        desired = self._repository.load_state(device.id) or LightState()

        try:
            await self._device.connect(_target_of(device))
            await self._reconcile(desired)
        except DeviceError as error:
            # Degradado, no fatal: queda constancia del fallo en el estado y el
            # llamante decide (502 en REST, arranque degradado en el lifespan).
            #
            # Cerrar el enlace ANTES de anotar el fallo es lo que impide que el
            # store y el adaptador digan cosas distintas: si `connect()` abrio
            # el enlace y `_reconcile` fallo, dejarlo abierto permitia encender
            # la tira por `/lights/power` con la UI diciendo "desconectado", y
            # abrir un segundo dispositivo encima del ya enlazado. `disconnect`
            # es idempotente, asi que llamarlo tambien cuando `connect()` fue lo
            # que fallo es seguro y evita duplicar el manejo.
            with suppress(Exception):
                await self._device.disconnect()
            await self._record_failure(device.id, error)
            raise

        async with self._store.mutate() as draft:
            draft.set_device(DeviceStatus(device_id=device.id, connected=True))
            draft.set_light(desired)
            draft.event = DeviceConnected(device_id=device.id)

        # `device.connected` solo lleva el id: sin esto, el resto de clientes se
        # quedarian mostrando la luz anterior a la rehidratacion.
        await self._store.publish_snapshot()

        return await self.status(device.id)

    async def try_connect(self, device_id: UUID) -> DeviceStatus:
        """Conecta sin propagar los fallos del hardware (ARCHITECTURE 7.5).

        Es el arranque degradado: un adaptador presente pero con la radio
        apagada, el controlador desenchufado o fuera de alcance **no** puede
        impedir que el servicio arranque ni tumbar `/health`. Lo que si es fatal
        es una *configuracion* invalida, y eso ocurre antes, al construir el
        adaptador (`build_light_device`), no aqui.
        """
        try:
            return await self.connect(device_id)
        except DeviceError as error:
            logger.warning(
                "Arranque degradado: no se pudo conectar el dispositivo %s (%s)",
                device_id,
                error,
            )
            return await self.status(device_id)

    async def disconnect(self, device_id: UUID) -> DeviceStatus:
        """Cierra el enlace. **Idempotente**: desconectar lo ya desconectado no falla.

        Sin cambio de estado no hay incremento de `version` ni evento: repetir
        la llamada no inunda a los clientes con desconexiones que no ocurrieron.
        """
        device = self.get_device(device_id)

        await self._device.disconnect()

        async with self._store.mutate() as draft:
            current = draft.state.device
            if current is not None and current.device_id == device.id and current.connected:
                draft.set_device(DeviceStatus(device_id=device.id, connected=False))
                draft.event = DeviceDisconnected(device_id=device.id)

        return await self.status(device.id)

    async def status(self, device_id: UUID) -> DeviceStatus:
        """Estado efimero del dispositivo. Nunca se lee de la base."""
        device = self.get_device(device_id)
        current = (await self._store.snapshot()).device
        if current is not None and current.device_id == device.id:
            return current
        return DeviceStatus(device_id=device.id, connected=False)

    async def _ensure_link_free(self, device_id: UUID) -> None:
        """El proceso mantiene un unico enlace; conectar otro lo secuestraria.

        Comprobacion deliberadamente fuera del cerrojo del store: la escritura
        en el dispositivo va antes que la mutacion, asi que no hay forma de
        reservar el enlace de manera atomica sin invertir el orden de
        operaciones. Con un unico enlace fisico y un solo worker, dos conexiones
        simultaneas exigen dos peticiones deliberadas a la vez.
        """
        current = (await self._store.snapshot()).device
        if current is not None and current.connected and current.device_id != device_id:
            raise DeviceBusyError(
                f"El dispositivo {current.device_id} ya esta conectado; "
                f"desconectalo antes de conectar {device_id}."
            )

    async def _reconcile(self, desired: LightState) -> None:
        """Reaplica el estado deseado sobre el hardware recien conectado.

        Las capacidades se usan aqui como **filtro** (no enviar lo que el
        hardware no sabe hacer), mientras que en `LightService` son una
        **guardia** (rechazar lo que el usuario pidio explicitamente). Misma
        informacion, reglas distintas: reconciliar no debe fallar porque una
        tira no tenga control de brillo.
        """
        await self._device.set_power(desired.power)
        if self._device.capabilities.rgb:
            await self._device.set_color(desired.color.r, desired.color.g, desired.color.b)
        if self._device.capabilities.brightness:
            await self._device.set_brightness(desired.brightness)

    async def _record_failure(self, device_id: UUID, error: DeviceError) -> None:
        """Deja el fallo visible en el estado global, sin publicar ningun evento.

        Ninguno de los nombres congelados de ARCHITECTURE 3.6 describe "intente
        conectar y no pude", y `device.disconnected` seria mentira: nunca hubo
        conexion. El llamante ya recibe el error (o el log, en arranque
        degradado).

        **Se guarda el codigo estable, no el texto del fallo.** `last_error`
        viaja en `GET /api/v1/state` y en `state.snapshot`, es decir a todos los
        clientes y sin autenticacion. Hoy la cadena la escribe el proyecto, pero
        en la Fase 1 la escribira Bleak, y sus mensajes incluyen la direccion del
        controlador y rutas de D-Bus. La politica de errores ya prohibe devolver
        el `str()` de un fallo interno; esto la respeta y ademas le da a la UI un
        valor sobre el que decidir, en vez de un texto que tendria que parsear.
        El texto completo queda en el log del servidor.

        Esta mutacion gasta una `version` sin publicar evento. Ese hueco es
        deliberado y ahora es detectable, porque el sobre de los frames lleva la
        version (ver `StateStore._publish`).
        """
        code = translate_error(error).code.value
        logger.warning("No se pudo abrir el enlace con %s [%s]: %s", device_id, code, error)

        async with self._store.mutate() as draft:
            draft.set_device(DeviceStatus(device_id=device_id, connected=False, last_error=code))


def _target_of(device: Device) -> DeviceTarget:
    """Traduce la identidad persistida al destino que entiende el adaptador.

    Un dispositivo sin direccion no se puede conectar: la direccion solo llega
    de un escaneo real, asi que una fila sin ella significa que nunca se emparejo
    con un controlador. Se traduce a `DeviceError` (502) y no a un fallo interno
    porque, desde fuera, el hecho es el mismo -- el backend no puede hablar con
    ese aparato -- y porque asi el arranque degradado del `lifespan`, que absorbe
    `DeviceError`, sigue arrancando en vez de tumbar el servicio.
    """
    if device.address is None:
        raise DeviceError(
            f"El dispositivo {device.name!r} no tiene direccion de transporte registrada: "
            "vuelve a descubrirlo con GET /api/v1/devices/scan."
        )
    return DeviceTarget(address=device.address)
