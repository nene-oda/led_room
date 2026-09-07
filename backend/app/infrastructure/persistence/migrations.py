"""Aplicar migraciones de Alembic desde codigo Python.

Existe para tres consumidores: el entrypoint del contenedor, la ejecucion
nativa en Windows y los tests. La CLI (`alembic upgrade head`) hace lo mismo
salvo por una cosa: NO comprueba la integridad del archivo ni traduce una base
corrupta a un mensaje accionable. El entrypoint usa este modulo por eso.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from alembic.config import Config

from alembic import command
from backend.app.config import REPO_ROOT, Settings, get_settings
from backend.app.infrastructure.persistence.database import (
    DatabaseCorruptedError,
    build_database_url,
    check_database_integrity,
    is_corruption,
)

logger = logging.getLogger("led_room.persistence")

#: EX_CONFIG de sysexits.h. Es el MISMO codigo que emite `docker-entrypoint.sh`
#: cuando el directorio de datos no es escribible, y por el mismo motivo: los
#: dos significan "hay que arreglar los datos o la configuracion; reintentar no
#: cambia nada". Se distinguen por el mensaje, no por el numero, y lo que
#: importa aqui es lo contrario: que NO se confunda con 75 (EX_TEMPFAIL,
#: cerrojo ocupado, reintentar tiene sentido) ni con 1 (la migracion fallo de
#: verdad y puede ir bien al siguiente intento).
#:
#: Sin esto, una base corrupta bajo `restart: unless-stopped` reintenta cada 60 s
#: para siempre: 90 minutos de la misma traza fue el sintoma real del incidente.
EXIT_DATA_CORRUPTED: Final = 78

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
    """Deja el esquema en `head`. Es idempotente: si ya lo esta, no hace nada.

    Comprueba la integridad ANTES de que Alembic abra nada. El orden no es
    cosmetico: sobre una base corrupta, la primera sentencia de Alembic es
    `PRAGMA main.table_info("alembic_version")` y lo que sube es una traza de
    SQLAlchemy que no dice ni el archivo afectado ni que hacer con el.
    """
    resolved = settings or get_settings()
    check_database_integrity(resolved.database)

    logger.info("Aplicando migraciones sobre %s", resolved.database)
    try:
        command.upgrade(build_alembic_config(resolved, ini_path), "head")
    except Exception as error:
        # Segunda red: `quick_check` puede pasar y la corrupcion aparecer al
        # leer una pagina que el chequeo rapido no recorre. El operador merece
        # el mismo mensaje en los dos casos.
        if is_corruption(error):
            raise DatabaseCorruptedError(resolved.database, str(error)) from error
        raise


def corruption_report(error: DatabaseCorruptedError) -> str:
    """Lo que ve el operador: que paso, por que y que hacer. Sin traza.

    La traza cruda de SQLAlchemy no le sirve a nadie a las tres de la manana, y
    repetida cada 60 segundos durante 90 minutos solo llena el disco.
    """
    return "\n".join(
        (
            f"led-room: la base de datos '{error.database}' esta corrupta: SQLite no la"
            " puede abrir.",
            f"led-room: detalle de SQLite: {error.detail}",
            "led-room: NO reintente: reiniciar el contenedor no repara el archivo.",
            "led-room: causa probable: SQLite en modo WAL sobre un bind mount"
            " virtualizado (Docker Desktop en Windows/macOS), o el mismo archivo"
            " abierto a la vez desde el host y desde el contenedor.",
            "led-room: que hacer:",
            "led-room:   1. Pare el contenedor y haga una copia del archivo antes de tocarlo.",
            "led-room:   2. Intente recuperarlo:"
            ' sqlite3 led-room.db ".recover" | sqlite3 led-room-nueva.db',
            "led-room:   3. Si no hay nada que salvar, borre el .db y sus vecinos"
            " -wal y -shm; el esquema se recrea solo en el siguiente arranque.",
            "led-room:   4. Guarde los datos en un volumen nombrado"
            " (-v led-room-data:/data), no en un bind mount de Windows, y no ejecute"
            " 'alembic upgrade head' en el host mientras el contenedor corre.",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada del entrypoint del contenedor. Devuelve el codigo de salida.

    Acepta la ruta del `alembic.ini` como unico argumento para no depender del
    directorio de trabajo, igual que hacia el `alembic -c /app/alembic.ini` al
    que sustituye.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    try:
        upgrade_to_head(settings, Path(args[0]) if args else None)
    except DatabaseCorruptedError as error:
        print(corruption_report(error), file=sys.stderr)
        return EXIT_DATA_CORRUPTED

    return 0


if __name__ == "__main__":  # pragma: no cover - se ejecuta como `python -m`
    raise SystemExit(main())
