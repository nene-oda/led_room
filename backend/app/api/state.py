"""`GET /state`: hidratacion por REST del estado global (README 31).

Devuelve exactamente el mismo cuerpo que el frame `state.snapshot` del
WebSocket. Un cliente que reconecta puede pedirlo por HTTP para cerrar el hueco
de los eventos que se perdio mientras estuvo fuera, sin un segundo formato que
mantener (NEXT_STEPS A4).
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.deps import StoreDep
from backend.app.api.schemas.state import GlobalStateRead

router = APIRouter(tags=["state"])


@router.get("/state", summary="Estado global del servidor")
async def read_state(store: StoreDep) -> GlobalStateRead:
    """El store en memoria es la fuente de verdad; la base no se lee en caliente."""
    return GlobalStateRead.from_domain(await store.snapshot())
