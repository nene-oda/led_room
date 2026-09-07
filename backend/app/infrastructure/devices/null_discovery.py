"""Descubrimiento de dispositivos sin radio.

Permite que `GET /devices/scan` responda en cualquier host: en Windows con
Docker Desktop, en los ejecutores de CI (que no tienen adaptador Bluetooth) y en
los tests. Ningun modulo de este paquete importa `bleak`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from backend.app.domain.devices.models import DiscoveredDevice

logger = logging.getLogger(__name__)


class NullDiscoveryAdapter:
    """Implementa `DeviceDiscoveryPort` devolviendo una lista fija.

    Vacia por defecto: es lo honesto cuando no hay radio. Se le puede pasar una
    lista para poblar la UI en una demostracion o en un test de integracion.

    `timeout_s` se ignora a proposito y se documenta aqui para que nadie lo lea
    como un olvido: sin radio no hay nada que esperar, y dormir el timeout haria
    que cada arranque de CI pagara diez segundos por una lista que ya se conoce.
    Es una diferencia observable respecto al escaner BLE, pero no rompe el
    contrato del puerto: lo que este promete es "lo visto durante como mucho
    `timeout_s` segundos", no una duracion minima.
    """

    def __init__(self, devices: Sequence[DiscoveredDevice] = ()) -> None:
        self._devices: tuple[DiscoveredDevice, ...] = tuple(devices)

    async def scan(self, timeout_s: float) -> Sequence[DiscoveredDevice]:
        logger.info(
            "Escaneo sin hardware (timeout=%.1fs ignorado): %d dispositivo(s)",
            timeout_s,
            len(self._devices),
        )
        return self._devices
