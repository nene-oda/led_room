"""Punto de entrada ASGI: backend.app.main:app."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.router import api_router
from backend.app.config import Settings, get_settings
from backend.app.infrastructure.devices.factory import build_light_device

logger = logging.getLogger("led_room")

#: Prefijos que el catch-all del SPA nunca debe resolver con index.html.
#: Sin esta guarda, GET /api/v1/typo devolveria HTML con 200 en vez de 404.
RESERVED_PREFIXES = frozenset({"api", "ws"})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Construye y libera las dependencias de larga duracion.

    Nada de esto ocurre al importar el modulo: importar la aplicacion no debe
    abrir hardware ni base de datos.
    """
    settings: Settings = app.state.settings
    logging.basicConfig(level=settings.log_level)

    app.state.light_device = build_light_device(settings)
    logger.info(
        "LED Room iniciado (adaptador=%s, frontend=%s)",
        settings.device_adapter,
        settings.frontend,
    )

    try:
        yield
    finally:
        await app.state.light_device.disconnect()
        logger.info("LED Room detenido")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    app = FastAPI(title="LED Room Controller", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved

    # El orden importa: en Starlette gana la primera ruta que hace match, y el
    # catch-all del SPA debe registrarse el ultimo.
    app.include_router(api_router)
    # Fase 4: app.add_api_websocket_route("/ws", websocket_endpoint)
    _mount_frontend(app, resolved.frontend if resolved.frontend_available else None)

    return app


def _mount_frontend(app: FastAPI, dist: Path | None) -> None:
    """Sirve el SPA compilado, si existe.

    No se usa StaticFiles(html=True) montado en "/": devuelve 404 en rutas
    profundas del cliente, con lo que recargar una URL interna romperia la
    aplicacion. Ver design.md D5.
    """
    if dist is None:
        logger.warning("Frontend no encontrado; el servicio arranca en modo solo API")

        @app.get("/", include_in_schema=False)
        async def _api_only_root() -> JSONResponse:
            return JSONResponse(
                {
                    "service": "led-room",
                    "mode": "api-only",
                    "docs": "/docs",
                    "hint": "Compile el frontend (npm run build) o defina LED_ROOM_FRONTEND",
                }
            )

        return

    root = dist.resolve()

    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def _serve_spa(spa_path: str) -> FileResponse:
        if spa_path.split("/", 1)[0] in RESERVED_PREFIXES:
            raise HTTPException(status_code=404, detail="Not Found")

        # Resolver un archivo real antes del fallback. Sin esto,
        # /manifest.webmanifest devolveria el HTML del indice con 200 y la PWA
        # de la Fase 8 no instalaria.
        if spa_path:
            candidate = (root / spa_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)

        return FileResponse(root / "index.html")


app = create_app()
