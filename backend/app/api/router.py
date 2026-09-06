"""Agregador de rutas de la API.

El prefijo /api/v1 se declara aqui UNA sola vez. Con el SPA servido por FastAPI,
mover rutas despues romperia el cliente y, mas adelante, el service worker.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api import health

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)

# Fase 2: devices, lights | Fase 5: effects | Fase 6: scenes | Fase 7: profiles
