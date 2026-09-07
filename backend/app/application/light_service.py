"""Casos de uso de control de la luz (README 16 y 17, NEXT_STEPS A2 y A4).

Una sola secuencia para REST y para WebSocket:

```text
comando -> validar (rango + capacidades) -> escribir en el dispositivo
        -> actualizar el store (version+1) -> publicar evento
```

Solo se publica lo que el dispositivo acepto. La escritura ocurre dentro del
`async with store.mutate()`, asi que un fallo del enlace sale por excepcion sin
cambiar el estado ni difundir nada.

**Aqui vive la guardia de capacidades**, y no en los adaptadores: "no ofrezcas
lo que el hardware no hace" es una regla de negocio, y ponerla en cada adaptador
la duplicaria tantas veces como familias de hardware haya. `DeviceCapabilityError`
estaba definido y no se lanzaba en ningun sitio; un puerto con capacidades que
nadie consulta es documentacion, no un seam.

El servicio es de **larga vida** (se construye una vez y se guarda en
`app.state`), porque el limitador del arrastre necesita una funcion estable a la
que aplicar el ultimo color. Por eso no persiste nada: durante un arrastre o un
efecto no se escribe en la base (NEXT_STEPS A3), y la persistencia del estado
deseado ante intencion del usuario necesita una sesion de vida corta que solo la
frontera HTTP sabe delimitar.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from backend.app.application.state_store import StateStore
from backend.app.domain.devices.ports import (
    DeviceCapabilityError,
    DeviceNotConnectedError,
    LightDevicePort,
)
from backend.app.domain.events import (
    LightBrightnessChanged,
    LightColorChanged,
    LightPowerChanged,
)
from backend.app.domain.lighting import LightState, RGBColor

#: Cancela lo que el motor de efectos este pintando. Se inyecta como funcion y
#: no como servicio para que `LightService` siga sin conocer al motor: solo
#: necesita poder decirle "quitate".
Preemption = Callable[[], Awaitable[None]]


async def require_connected(store: StateStore) -> None:
    """La fuente de verdad de "conectado" es el STORE, no el adaptador.

    Las dos preguntas tenian antes dos respuestas: esta guardia consultaba
    `device.is_connected` y `DeviceService._ensure_link_free` consultaba el
    store. Cuando divergian (una reconciliacion fallida dejaba el enlace abierto
    y el estado a `connected: false`), `POST /lights/power` respondia 200 y
    encendia la tira mientras la UI decia "desconectado".

    Manda el store porque es el titular autoritativo declarado -- SQLite es
    cache de arranque y el adaptador es un sumidero (NEXT_STEPS A4) -- y porque
    el adaptador no puede responder la otra mitad de la pregunta:
    `LightDevicePort` no expone QUE dispositivo ocupa el enlace, y sin eso
    `_ensure_link_free` no podria decidir nada. Un unico consultado, ninguna
    divergencia posible.

    Si el enlace se cayera por debajo sin que el store se entere, la escritura
    fallara y saldra un 502 `device_write_failed`, que es la respuesta honesta.

    Es una funcion de modulo y no un metodo privado porque el motor de efectos
    aplica **la misma** regla antes de arrancar un plan: duplicarla alli seria
    duplicar una regla de negocio, no un detalle.
    """
    device = (await store.snapshot()).device
    if device is None or not device.connected:
        raise DeviceNotConnectedError(
            "No hay ningun dispositivo conectado: conecta uno antes de operar la luz."
        )


class LightService:
    """Encender, colorear y atenuar la unica luz conectada.

    No recibe `device_id`: el contrato de `/lights/*` esta congelado sin el
    (README 16) y el proceso mantiene un unico enlace. Resolver "cual" es
    trabajo de `DeviceService`, que es quien decide que dispositivo ocupa ese
    enlace.
    """

    def __init__(
        self,
        device: LightDevicePort,
        store: StateStore,
        *,
        preempt: Preemption | None = None,
    ) -> None:
        """`preempt` para el efecto activo antes de aplicar un comando manual.

        Es opcional para que un test pueda construir el servicio sin motor, pero
        en la aplicacion real se cablea siempre: sin el, el siguiente fotograma
        pisaria el color que acaba de elegir el usuario 50 ms despues y el
        control pareceria roto (NEXT_STEPS 6.4).
        """
        self._device = device
        self._store = store
        self._preempt = preempt

    async def set_power(self, value: bool) -> LightState:
        """Enciende o apaga. Ningun hardware de esta clase carece de encendido."""
        await require_connected(self._store)
        await self._take_over()

        async with self._store.mutate() as draft:
            current = draft.state.light
            light = LightState(power=value, color=current.color, brightness=current.brightness)

            await self._device.set_power(value)

            draft.set_light(light)
            draft.event = LightPowerChanged(power=value)

        return draft.state.light

    async def set_color(self, color: RGBColor) -> LightState:
        """Fija el color. Requiere la capacidad `rgb`."""
        await require_connected(self._store)
        self._require(self._device.capabilities.rgb, capability="rgb", operation="fijar el color")
        await self._take_over()

        async with self._store.mutate() as draft:
            current = draft.state.light
            light = LightState(power=current.power, color=color, brightness=current.brightness)

            await self._device.set_color(color.r, color.g, color.b)

            draft.set_light(light)
            # El evento lleva el `RGBColor` de dominio: convertirlo a `#RRGGBB`
            # es decision del transporte (ARCHITECTURE 3.2).
            draft.event = LightColorChanged(color=color)

        return draft.state.light

    async def set_brightness(self, brightness: int) -> LightState:
        """Fija el brillo 0-100. Requiere la capacidad `brightness`."""
        await require_connected(self._store)
        self._require(
            self._device.capabilities.brightness,
            capability="brightness",
            operation="fijar el brillo",
        )
        await self._take_over()

        async with self._store.mutate() as draft:
            current = draft.state.light
            # Construir el estado ANTES de escribir valida el rango una sola vez
            # y en un solo sitio: `Percent` ya es la definicion del 0-100 del
            # dominio. Un valor invalido lanza `ValueError` (422) sin que el
            # dispositivo llegue a recibir nada.
            light = LightState(power=current.power, color=current.color, brightness=brightness)

            await self._device.set_brightness(brightness)

            draft.set_light(light)
            draft.event = LightBrightnessChanged(brightness=brightness)

        return draft.state.light

    async def _take_over(self) -> None:
        """Un comando manual gana al efecto en curso.

        Se llama DESPUES de validar (enlace y capacidades) y ANTES de escribir:
        cancelar el efecto para responder luego un 409 dejaria la tira parada
        por un comando que se rechazo.
        """
        if self._preempt is not None:
            await self._preempt()

    def _require(self, supported: bool, *, capability: str, operation: str) -> None:
        """Guardia de capacidades: se comprueba antes de tocar el dispositivo.

        El adaptador no recibe ninguna escritura cuando la capacidad falta; esa
        es justamente la garantia que hace util el campo `capabilities`.
        """
        if not supported:
            raise DeviceCapabilityError(
                f"El dispositivo no soporta '{capability}': no se puede {operation}."
            )
