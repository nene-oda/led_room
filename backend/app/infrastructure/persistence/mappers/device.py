"""Dominio de dispositivos <-> filas de `devices`, `device_capabilities` y `device_state`.

UNICO lugar del proyecto donde conviven los dos vocabularios. Existe por dos
motivos verificados contra el codigo, no por simetria arquitectonica:

1. **Los nombres no coinciden.** El dominio dice `rgb`, `brightness`, `effects`,
   `segments`; las columnas dicen `supports_rgb`, `supports_brightness`,
   `supports_effects`, `supports_segments`. Se conservan ambos a proposito: una
   columna booleana llamada `brightness` en `device_capabilities`, junto a una
   entera 0-100 llamada `brightness` en `device_state`, es una trampa para quien
   lea un backup o escriba SQL a mano (ARCHITECTURE 5.4). Si la cadena
   `supports_` aparece fuera de este modulo, la frontera esta rota.
2. **`device_state.color_hex` tiene un `CHECK ... GLOB '#[0-9A-F]...'`**, y GLOB
   distingue mayusculas: guardar `#7b00ff` lanza `IntegrityError`. Por eso el
   color se serializa SIEMPRE con `RGBColor.to_hex()`, que emite mayusculas
   (ARCHITECTURE 3.2).

Las funciones `apply_*_to_record` mutan un `*Record` ya existente en vez de
construir uno nuevo: sustituir la fila obligaria a reconstruir tambien las
relaciones y perderia `created_at`. Nunca tocan la clave primaria, porque el
`upsert` puede haber resuelto la fila por `(adapter_type, ble_address)` y
reescribir el `id` dejaria huerfanas las filas hijas.
"""

from __future__ import annotations

from backend.app.domain.devices.models import Device, DeviceCapabilities, DeviceType
from backend.app.domain.lighting import LightState, RGBColor
from backend.app.infrastructure.persistence.models.base import utc_now
from backend.app.infrastructure.persistence.models.device import (
    DeviceCapabilitiesRecord,
    DeviceRecord,
    DeviceStateRecord,
)


class DeviceMappingError(Exception):
    """Una fila persistida no se puede traducir a dominio.

    NO hereda de `ValueError` a proposito: la politica de errores mapea los
    `ValueError` de rango a `422 Unprocessable Entity`, y una fila corrupta no es
    una peticion invalida del cliente, sino un fallo del servidor
    (NEXT_STEPS A6).
    """


def adapter_type_to_column(adapter_type: DeviceType) -> str:
    """Valor que se guarda en `devices.adapter_type`.

    La columna es texto libre, pero `DeviceType` es el unico vocabulario de
    adaptador del proyecto (NEXT_STEPS A1). Que la conversion viva aqui evita
    que un repositorio o un servicio construyan la cadena por su cuenta.
    """
    return adapter_type.value


def _adapter_type_to_domain(value: str) -> DeviceType:
    try:
        return DeviceType(value)
    except ValueError as exc:
        known = ", ".join(sorted(member.value for member in DeviceType))
        raise DeviceMappingError(
            f"adapter_type desconocido en la base de datos: {value!r}."
            f" Valores validos: {known}."
            f" Degradar en silencio ocultaria una fila escrita a mano o por una"
            f" version con mas adaptadores que esta."
        ) from exc


def _capabilities_to_domain(record: DeviceCapabilitiesRecord) -> DeviceCapabilities:
    return DeviceCapabilities(
        rgb=record.supports_rgb,
        brightness=record.supports_brightness,
        effects=record.supports_effects,
        addressable=record.addressable,
        segments=record.supports_segments,
        white_channel=record.white_channel,
        music_mode=record.music_mode,
    )


def _apply_capabilities(record: DeviceCapabilitiesRecord, caps: DeviceCapabilities) -> None:
    record.supports_rgb = caps.rgb
    record.supports_brightness = caps.brightness
    record.supports_effects = caps.effects
    record.addressable = caps.addressable
    record.supports_segments = caps.segments
    record.white_channel = caps.white_channel
    record.music_mode = caps.music_mode


def device_to_domain(record: DeviceRecord) -> Device:
    """Reconstruye la identidad de dominio a partir de la fila y su 1:1 de capacidades."""
    if record.capabilities is None:
        raise DeviceMappingError(
            f"El dispositivo {record.id} no tiene fila en device_capabilities."
            f" La relacion es 1:1 y el repositorio la escribe siempre; una fila"
            f" sin capacidades solo puede venir de una insercion manual."
        )

    return Device(
        id=record.id,
        name=record.name,
        adapter_type=_adapter_type_to_domain(record.adapter_type),
        address=record.ble_address,
        enabled=record.enabled,
        auto_connect=record.auto_connect,
        capabilities=_capabilities_to_domain(record.capabilities),
    )


def apply_device_to_record(record: DeviceRecord, device: Device) -> None:
    """Vuelca la identidad de dominio sobre la fila, creando el 1:1 si falta.

    `ble_name` NO se toca: es metadato de diagnostico del escaneo que el dominio
    no modela, y sobreescribirlo con nada lo borraria en cada guardado.
    """
    record.name = device.name
    record.adapter_type = adapter_type_to_column(device.adapter_type)
    record.ble_address = device.address
    record.enabled = device.enabled
    record.auto_connect = device.auto_connect
    record.updated_at = utc_now()

    if record.capabilities is None:
        record.capabilities = DeviceCapabilitiesRecord(device_id=record.id)
    _apply_capabilities(record.capabilities, device.capabilities)


def state_to_domain(record: DeviceStateRecord) -> LightState:
    """Ultimo estado deseado. `connected` y `rssi` no estan aqui: no se persisten."""
    try:
        color = RGBColor.from_hex(record.color_hex)
    except ValueError as exc:
        raise DeviceMappingError(
            f"color_hex invalido para el dispositivo {record.device_id}:"
            f" {record.color_hex!r}. El CHECK de la tabla deberia haberlo impedido."
        ) from exc

    return LightState(power=record.power, color=color, brightness=record.brightness)


def apply_state_to_record(record: DeviceStateRecord, state: LightState) -> None:
    """Vuelca el estado deseado sobre la fila.

    `active_scene_id` y `active_effect_id` quedan intactos: sus tablas todavia no
    tienen caso de uso propietario (ARCHITECTURE 7.5).
    """
    record.power = state.power
    # to_hex() emite MAYUSCULAS. Es lo que exige el CHECK ... GLOB de la tabla.
    record.color_hex = state.color.to_hex()
    record.brightness = state.brightness
    record.updated_at = utc_now()
