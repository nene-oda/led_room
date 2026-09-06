"""Aplicar migraciones de Alembic desde codigo Python.

Existe para tres consumidores: el entrypoint del contenedor, la ejecucion
nativa en Windows y los tests. La CLI (`alembic upgrade head`) sigue siendo
valida y hace exactamente lo mismo.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config

from alembic import command
from backend.app.config import REPO_ROOT, Settings, get_settings
from backend.app.infrastructure.persistence.database import build_database_url

logger = logging.getLogger("led_room.persistence")

#: Sitios donde buscar alembic.ini, en orden. El primero cubre la ejecucion
#: nativa desde el repositorio; el segundo, el contenedor (WORKDIR /app), donde
#: `REPO_ROOT` apunta a site-packages y no sirve.
_INI_CANDIDATES = (REPO_ROOT / "alembic.ini", Path.cwd() / "alembic.ini")


def find_alembic_ini() -> Path:
    for candidate in _INI_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "No se encontro alembic.ini en "
        + ", ".join(str(c) for c in _INI_CANDIDATES)
        + ". En el contenedor debe copiarse a /app/alembic.ini junto con /app/alembic/."
    )


def build_alembic_config(settings: Settings, ini_path: Path | None = None) -> Config:
    ini = ini_path or find_alembic_ini()
    config = Config(str(ini))
    # La URL manda desde la configuracion de la aplicacion, no desde el .ini:
    # asi la migracion no puede tocar un archivo distinto del que abre FastAPI.
    config.set_main_option("sqlalchemy.url", build_database_url(settings.database))
    return config


def upgrade_to_head(settings: Settings | None = None, ini_path: Path | None = None) -> None:
    """Deja el esquema en `head`. Es idempotente: si ya lo esta, no hace nada."""
    resolved = settings or get_settings()
    logger.info("Aplicando migraciones sobre %s", resolved.database)
    command.upgrade(build_alembic_config(resolved, ini_path), "head")


def main() -> None:  # pragma: no cover - punto de entrada del entrypoint
    logging.basicConfig(level=get_settings().log_level)
    upgrade_to_head()


if __name__ == "__main__":  # pragma: no cover
    main()
