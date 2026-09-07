"""Agregador de rutas de la API.

El prefijo /api/v1 se declara aqui UNA sola vez. Con el SPA servido por FastAPI,
mover rutas despues romperia el cliente y, mas adelante, el service worker.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api import devices, effects, health, lights, profiles, scenes, state, system

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
api_router.include_router(devices.router)
api_router.include_router(effects.router)
api_router.include_router(lights.router)
api_router.include_router(profiles.router)
api_router.include_router(scenes.router)
api_router.include_router(state.router)
api_router.include_router(system.router)
