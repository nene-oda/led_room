"""Punto de entrada ASGI: backend.app.main:app."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.deps import AppResources, build_device_service
from backend.app.api.errors import register_exception_handlers
from backend.app.api.router import api_router
from backend.app.application.effect_runner import EffectRunner
from backend.app.application.effect_service import EffectPlayer
from backend.app.application.light_service import LightService
from backend.app.application.state_store import StateStore
from backend.app.application.throttle import LastValueThrottle, LightThrottles
from backend.app.config import Settings, get_settings
from backend.app.domain.devices.ports import LightDevicePort
from backend.app.infrastructure.clock import SystemClock
from backend.app.infrastructure.devices.factory import (
    build_device_discovery,
    build_light_device,
    supports_discovery,
)
from backend.app.infrastructure.persistence.database import create_database_engine, session_scope
from backend.app.infrastructure.persistence.repositories import SQLModelDeviceRepository
from backend.app.websocket.manager import ConnectionManager
from backend.app.websocket.routes import (
    reporting_brightness_applier,
    reporting_color_applier,
    websocket_endpoint,
)

logger = logging.getLogger("led_room")

#: Prefijos que el catch-all del SPA nunca debe resolver con index.html.
#: Sin esta guarda, GET /api/v1/typo devolveria HTML con 200 en vez de 404.
RESERVED_PREFIXES = frozenset({"api", "ws"})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Construye y libera las dependencias de larga duracion.

    Nada de esto ocurre al importar el modulo: importar la aplicacion no debe
    abrir hardware ni base de datos.

    **Semantica de fallo, asimetrica a proposito** (ARCHITECTURE 7.5): una
    *configuracion invalida* (un adaptador sin constructor registrado) revienta
    aqui y el servicio no arranca, porque servir con una configuracion que nadie
    puede cumplir solo aplaza el error. En cambio el *hardware ausente* o un
    `connect()` fallido dejan arrancar igual: `/api/v1/health` sigue en 200 y el
    estado global dice `connected: false`.
    """
    settings: Settings = app.state.settings
    logging.basicConfig(level=settings.log_level)

    async with AsyncExitStack() as stack:
        # Cada recurso registra su liberacion EN CUANTO se construye. Asi el
        # cierre no depende de que todo lo anterior haya ido bien: antes, un
        # `disconnect()` que lanzara dejaba el engine sin cerrar y el WAL sin
        # checkpoint.
        engine = create_database_engine(settings.database)
        stack.callback(engine.dispose)

        connections = ConnectionManager()
        stack.push_async_callback(connections.close_all)

        # Configuracion: si el adaptador no existe, esto lanza y el servicio no
        # arranca. Es deliberado.
        light_device = build_light_device(settings)
        discovery = build_device_discovery(settings)
        stack.push_async_callback(_release_device, light_device, settings.ble_write_timeout)

        store = StateStore(connections)

        # El motor se construye ANTES que `LightService` porque este lo recibe
        # como funcion de preempcion: cualquier comando manual cancela el efecto
        # en curso antes de escribir, o el siguiente fotograma pisaria el color
        # que acaba de elegir el usuario 50 ms despues (NEXT_STEPS 6.4).
        effects = EffectPlayer(EffectRunner(light_device, SystemClock()), store)
        stack.push_async_callback(effects.stop)

        light_service = LightService(light_device, store, preempt=effects.stop)
        interval_s = settings.throttle_interval_ms / 1000
        throttles = LightThrottles(
            color=LastValueThrottle(
                reporting_color_applier(light_service, connections, store),
                interval_s=interval_s,
            ),
            brightness=LastValueThrottle(
                reporting_brightness_applier(light_service, connections, store),
                interval_s=interval_s,
            ),
        )
        stack.push_async_callback(throttles.cancel_all)

        resources = AppResources(
            settings=settings,
            engine=engine,
            light_device=light_device,
            discovery=discovery,
            supports_discovery=supports_discovery(settings),
            store=store,
            light=light_service,
            throttles=throttles,
            connections=connections,
            effects=effects,
            scan_lock=asyncio.Lock(),
        )
        app.state.resources = resources

        logger.info(
            "LED Room iniciado (adaptador=%s, base=%s, frontend=%s)",
            settings.device_adapter,
            settings.database,
            settings.frontend,
        )

        await _auto_connect(resources)

        try:
            yield
        finally:
            # El orden de cierre es el inverso al de registro: primero se
            # dejan de aplicar arrastres, luego se para el efecto en curso,
            # despues se suelta el enlace, se cortan los sockets y por ultimo se
            # cierra SQLite. Parar el efecto NO apaga la luz: el ultimo
            # fotograma se queda puesto.
            logger.info("LED Room detenido")


async def _release_device(device: LightDevicePort, timeout_s: float) -> None:
    """Suelta el enlace sin que el apagado pueda colgarse.

    `SerializedLightDevice.disconnect` delega sin timeout a proposito (debe poder
    cortar, no esperar turno), asi que un `BleakClient.disconnect()` colgado
    bloquearia el `lifespan` para siempre: Docker mataria el contenedor a los
    10 s y el WAL de SQLite se quedaria sin checkpoint. Se acota con el timeout
    de escritura, que es la misma cota que ya gobierna el enlace.
    """
    with suppress(Exception):
        await asyncio.wait_for(device.disconnect(), timeout_s)


async def _auto_connect(resources: AppResources) -> None:
    """Intenta abrir el enlace con el primer dispositivo marcado `auto_connect`.

    Es el arranque degradado. Ningun fallo de aqui puede impedir que el servicio
    atienda peticiones:

    * el hardware apagado o fuera de alcance lo absorbe `try_connect`;
    * un esquema todavia sin migrar (ejecucion nativa sin `alembic upgrade
      head`) se registra y se sigue. La garantia del esquema vive en
      `docker-entrypoint.sh`, ANTES de arrancar uvicorn, no en el `lifespan`.

    Se elige un solo dispositivo porque el proceso mantiene un solo enlace.
    """
    try:
        with session_scope(resources.engine) as session:
            service = build_device_service(
                repository=SQLModelDeviceRepository(session),
                discovery=resources.discovery,
                resources=resources,
            )
            device = next(
                (candidate for candidate in service.list_devices() if candidate.auto_connect),
                None,
            )
            if device is None:
                logger.info("Ningun dispositivo con auto_connect: se arranca sin enlace")
                return

            status = await service.try_connect(device.id)
    except Exception as error:
        logger.warning("Arranque sin enlace de dispositivo: %s", error)
        return

    logger.info(
        "Arranque con %s: connected=%s%s",
        device.name,
        status.connected,
        f" ({status.last_error})" if status.last_error else "",
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    app = FastAPI(title="LED Room Controller", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved

    register_exception_handlers(app)

    # El orden importa: en Starlette gana la primera ruta que hace match, y el
    # catch-all del SPA debe registrarse el ultimo.
    app.include_router(api_router)
    app.add_api_websocket_route("/ws", websocket_endpoint, name="websocket")
    _mount_frontend(app, resolved.frontend if resolved.frontend_available else None)

    return app


def _mount_frontend(app: FastAPI, dist: Path | None) -> None:
    """Sirve el SPA compilado, si existe.

    No se usa StaticFiles(html=True) montado en "/": devuelve 404 en rutas
    profundas del cliente, con lo que recargar una URL interna romperia la
    aplicacion. Ver ARCHITECTURE 3.1.
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
