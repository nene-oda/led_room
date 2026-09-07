"""Guardianes automaticos de los limites de capas.

Un riesgo sin test es un recordatorio. Estas dos reglas son las que sostienen el
seam del proyecto (ARCHITECTURE 4, NEXT_STEPS A1 y A3), y ninguna de las dos se
puede comprobar leyendo un diff.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.domain.devices.models import DeviceCapabilities
from backend.app.infrastructure.persistence.models.device import DeviceCapabilitiesRecord
from backend.tests.imports import forbidden_import, imports_of

# backend/tests/test_architecture.py -> backend/tests -> backend -> raiz
REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_ROOT = REPO_ROOT / "backend" / "app" / "domain"
DOMAIN_MODULES = sorted(DOMAIN_ROOT.rglob("*.py"))

#: Todo lo que el dominio no puede conocer. Los cuatro primeros son bibliotecas
#: de transporte o de persistencia; los demas son capas exteriores: importarlas
#: invertiria la direccion de las dependencias (y `config` crearia un ciclo,
#: porque `Settings` ya importa `DeviceType`).
FORBIDDEN_IMPORTS = (
    "sqlmodel",
    "sqlalchemy",
    "bleak",
    "fastapi",
    "backend.app.infrastructure",
    "backend.app.application",
    "backend.app.api",
    "backend.app.websocket",
    "backend.app.config",
)


def test_hay_modulos_de_dominio_que_vigilar() -> None:
    """Una lista vacia haria que el guardian de imports pasara sin comprobar nada."""
    assert DOMAIN_MODULES, f"No se encontro ningun modulo de dominio en {DOMAIN_ROOT}"


@pytest.mark.parametrize(
    "module_path",
    DOMAIN_MODULES,
    ids=[path.relative_to(DOMAIN_ROOT).as_posix() for path in DOMAIN_MODULES],
)
def test_el_dominio_no_importa_infraestructura_ni_frameworks(module_path: Path) -> None:
    relative = module_path.relative_to(REPO_ROOT)

    for imported, lineno in imports_of(module_path):
        for forbidden in FORBIDDEN_IMPORTS:
            assert not forbidden_import(imported, forbidden), (
                f"{relative}:{lineno} importa {imported!r}. El dominio debe ser "
                f"independiente de FastAPI, Bleak, SQLModel y de la infraestructura "
                f"(ARCHITECTURE 4)."
            )


def test_las_capacidades_del_dominio_cubren_las_columnas_persistidas() -> None:
    """Añadir una columna de capacidad y olvidar el dominio debe romper la build.

    Los nombres difieren a proposito (`supports_rgb` ↔ `rgb`, ARCHITECTURE 5.4):
    lo que se compara es el conjunto tras deshacer ese prefijo, que es
    exactamente lo que tendra que hacer el mapper.
    """
    columns = {
        name.removeprefix("supports_")
        for name in DeviceCapabilitiesRecord.model_fields
        if name != "device_id"
    }

    assert columns == set(DeviceCapabilities.model_fields)
