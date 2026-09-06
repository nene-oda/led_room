"""Motor y sesiones SQLite.

`LED_ROOM_DATABASE` es una RUTA de sistema de archivos, no una URL: en Windows
`<repo>/data/led-room.db` y en el contenedor `/data/led-room.db`. La conversion
a URL vive aqui y en ningun otro sitio.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePath
from typing import Any

from sqlalchemy import Engine, event
from sqlalchemy.pool import Pool, StaticPool
from sqlmodel import Session, SQLModel, create_engine

# El import registra las diez tablas en SQLModel.metadata. No es decorativo:
# sin el, create_all no crea nada y los mappers no se pueden configurar.
from backend.app.infrastructure.persistence import models as _models  # noqa: F401

logger = logging.getLogger("led_room.persistence")

#: URL de una base efimera en memoria, para tests.
IN_MEMORY_URL = "sqlite://"


def url_from_absolute_path(path: PurePath) -> str:
    """Formatea una ruta ABSOLUTA como URL de SQLAlchemy.

    Funcion pura y separada de `build_database_url` para poder comprobar los
    dos hosts del proyecto desde cualquiera de ellos: `Path.resolve()` en
    Windows ancla `/data/led-room.db` a la unidad actual (`C:/data/...`) y
    hace imposible validar ahi el caso del contenedor.

    - `/data/led-room.db`          -> `sqlite:////data/led-room.db`
    - una ruta de Windows -> `sqlite:///C:/repo/data/led-room.db`

    Las cuatro barras del caso Linux no son una errata: `sqlite:///` lleva
    tres y la ruta POSIX absoluta aporta la cuarta. Se usa `as_posix()` porque
    una barra invertida de Windows dentro de una URL no separa nada.
    """
    return f"sqlite:///{path.as_posix()}"


def build_database_url(database: Path) -> str:
    """URL a partir del valor de `LED_ROOM_DATABASE`, que es una RUTA."""
    return url_from_absolute_path(Path(database).expanduser().resolve())


def create_database_engine(
    database: Path | None = None,
    *,
    url: str | None = None,
    echo: bool = False,
    poolclass: type[Pool] | None = None,
) -> Engine:
    """Crea el engine y deja SQLite en un estado utilizable.

    `check_same_thread=False` es obligatorio: FastAPI ejecuta las dependencias
    sincronas en un hilo del threadpool distinto en cada peticion, y el guardia
    por defecto de sqlite3 abortaria. La seguridad la aporta el pool, que no
    presta la misma conexion a dos hilos a la vez.
    """
    if url is None:
        if database is None:
            raise ValueError("Indique `database` o `url`")
        # SQLite no crea el directorio contenedor: sin esto, el primer arranque
        # con un volumen vacio falla con "unable to open database file".
        Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        url = build_database_url(database)

    kwargs: dict[str, Any] = {
        "echo": echo,
        "connect_args": {"check_same_thread": False},
    }

    if poolclass is not None:
        kwargs["poolclass"] = poolclass
    elif url == IN_MEMORY_URL or ":memory:" in url:
        # Sin StaticPool cada conexion abriria una base en memoria distinta y
        # las tablas creadas desaparecerian (LED_ROOM_DATABASE_MODEL 51).
        kwargs["poolclass"] = StaticPool

    engine = create_engine(url, **kwargs)
    _install_sqlite_pragmas(engine)
    return engine


def _install_sqlite_pragmas(engine: Engine) -> None:
    """Aplica los PRAGMA en CADA conexion nueva del pool.

    `PRAGMA foreign_keys` esta APAGADO por defecto en SQLite y no es una
    propiedad de la base, sino de la conexion: sin este listener, todos los
    `ON DELETE CASCADE` y `RESTRICT` del esquema serian decorativos.
    """

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, connection_record: Any) -> None:
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return

        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")

            # WAL permite leer mientras se escribe y reduce los bloqueos. No se
            # intenta en memoria, y si el sistema de archivos no lo soporta
            # (algunos montajes de red o bind mounts) se degrada a journal
            # normal en vez de impedir el arranque.
            if engine.url.database not in (None, ":memory:"):
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                except sqlite3.Error:
                    logger.warning(
                        "No se pudo activar WAL; se continua con el journal por defecto",
                        exc_info=True,
                    )

            # Espera en vez de fallar de inmediato si otra conexion escribe.
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


def create_all(engine: Engine) -> None:
    """Crea el esquema sin Alembic.

    Solo para tests y bases efimeras. En el despliegue real manda Alembic
    (LED_ROOM_DATABASE_MODEL 47).
    """
    SQLModel.metadata.create_all(engine)


def session_factory(engine: Engine) -> Iterator[Session]:
    """Dependencia de FastAPI: `Depends(...)` sobre un generador SINCRONO.

    Al no ser `async`, Starlette lo ejecuta en el threadpool y la sesion
    bloqueante no detiene el bucle de eventos donde vive BLE.
    """
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Sesion transaccional para codigo que no es una peticion HTTP."""
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
