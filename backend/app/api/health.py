"""Endpoint de salud (README 16)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Contrato exacto del README: {"status": "ok"}."""

    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse, summary="Estado del servicio")
async def read_health() -> HealthResponse:
    """Responde 200 siempre que el proceso acepte peticiones.

    Deliberadamente NO refleja el estado del dispositivo ni del Bluetooth: es lo
    que consume el HEALTHCHECK del contenedor y no debe caerse porque no haya
    lampara. Los diagnosticos iran a un endpoint de estado (README 31).
    """
    return HealthResponse()
