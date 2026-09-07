"""Implementacion real del puerto de tiempo.

Adaptador de dos lineas contra `asyncio` y `time`. Vive en infraestructura
porque `asyncio.sleep` es un detalle del entorno de ejecucion, no una regla de
negocio; la capa de aplicacion solo conoce `Clock`.
"""

from __future__ import annotations

import asyncio
import time


class SystemClock:
    """Cumple `backend.app.application.clock.Clock`."""

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
