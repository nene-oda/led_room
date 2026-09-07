"""Traduccion entre modelos de dominio y filas de SQLModel.

Este paquete es la frontera: por encima de el solo circulan tipos de dominio
(`Device`, `LightState`), por debajo solo `*Record`. Ningun servicio ni router
puede conocer el nombre de una columna (ARCHITECTURE 5.4,
LED_ROOM_DATABASE_MODEL 53).

Solo hay mapper de dispositivos. `effects`, `scenes`, `profiles` y `schedules`
existen en el esquema pero no tienen caso de uso propietario, y la regla vigente
es que una tabla asi no se expone, no se siembra y no tiene repositorio ni
mapper (ARCHITECTURE 7.5).
"""

from __future__ import annotations

from backend.app.infrastructure.persistence.mappers.device import (
    DeviceMappingError,
    adapter_type_to_column,
    apply_device_to_record,
    apply_state_to_record,
    device_to_domain,
    state_to_domain,
)

__all__ = [
    "DeviceMappingError",
    "adapter_type_to_column",
    "apply_device_to_record",
    "apply_state_to_record",
    "device_to_domain",
    "state_to_domain",
]
