"""Seleccion del adaptador de dispositivo segun la configuracion.

Este modulo es el unico que conoce a la vez el puerto y sus implementaciones.
El dominio y la capa de aplicacion solo ven `LightDevicePort`.
"""

from __future__ import annotations

from backend.app.config import Settings
from backend.app.domain.devices.ports import LightDevicePort
from backend.app.infrastructure.devices.null_adapter import NullLightDeviceAdapter


def build_light_device(settings: Settings) -> LightDevicePort:
    """Construye el adaptador indicado por `LED_ROOM_DEVICE_ADAPTER`."""
    if settings.device_adapter == "null":
        return NullLightDeviceAdapter()

    if settings.device_adapter == "lotus_lantern":
        # No se implementa hasta completar la Fase 0 del README: hacen falta el
        # nombre BLE real, los UUID de servicio y caracteristica, y los bytes de
        # comando verificados contra el hardware. Inventarlos aqui produciria un
        # adaptador que parece funcionar y no funciona.
        raise NotImplementedError(
            "El adaptador LotusLantern llega en la Fase 1; requiere el protocolo "
            "verificado contra el hardware (README 33, Fase 0). "
            "Use LED_ROOM_DEVICE_ADAPTER=null mientras tanto."
        )

    raise ValueError(f"Adaptador de dispositivo desconocido: {settings.device_adapter!r}")
