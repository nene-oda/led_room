"""Guardian de la direccion de dependencias de la capa de aplicacion.

`backend/tests/test_architecture.py` vigila el dominio; este vigila la capa que
esta justo encima. La regla que sostiene el diseño (NEXT_STEPS A4) es que
`application/` publique a traves de `EventPublisher` y **nunca** importe el
gestor de WebSocket: en cuanto un servicio importe el transporte, el puerto se
vuelve decorativo y el motor de efectos de la Fase 5 heredara el acoplamiento.

Se sigue el mismo enfoque con `ast` porque leer los imports en un diff no es una
comprobacion: es un recordatorio.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.tests.imports import forbidden_import, imports_of

# backend/tests/test_application_boundaries.py -> backend/tests -> backend -> raiz
REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = REPO_ROOT / "backend" / "app" / "application"
APPLICATION_MODULES = sorted(APPLICATION_ROOT.rglob("*.py"))

#: La capa de aplicacion depende de abstracciones: puertos de dominio y tipos de
#: dominio. Todo lo de esta lista es transporte, persistencia concreta o una
#: capa exterior.
FORBIDDEN_IMPORTS = (
    "fastapi",
    "starlette",
    "sqlmodel",
    "sqlalchemy",
    "bleak",
    "backend.app.websocket",
    "backend.app.api",
    "backend.app.infrastructure",
    "backend.app.main",
)


def test_hay_modulos_de_aplicacion_que_vigilar() -> None:
    assert APPLICATION_MODULES, f"No se encontro ningun modulo en {APPLICATION_ROOT}"


@pytest.mark.parametrize(
    "module_path",
    APPLICATION_MODULES,
    ids=[path.relative_to(APPLICATION_ROOT).as_posix() for path in APPLICATION_MODULES],
)
def test_la_aplicacion_no_importa_el_transporte_ni_la_infraestructura(module_path: Path) -> None:
    relative = module_path.relative_to(REPO_ROOT)

    for imported, lineno in imports_of(module_path):
        for forbidden in FORBIDDEN_IMPORTS:
            assert not forbidden_import(imported, forbidden), (
                f"{relative}:{lineno} importa {imported!r}. La capa de aplicacion "
                f"depende de puertos, no de implementaciones: publica con "
                f"`EventPublisher` y habla con el hardware por `LightDevicePort` "
                f"(NEXT_STEPS A4)."
            )
