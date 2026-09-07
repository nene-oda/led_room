"""Motor y sesiones SQLite.

`LED_ROOM_DATABASE` es una RUTA de sistema de archivos, no una URL: en Windows
`<repo>/data/led-room.db` y en el contenedor `/data/led-room.db`. La conversion
a URL vive aqui y en ningun otro sitio.

Aqui vive tambien lo que sabe distinguir un archivo SQLite sano de uno corrupto
(`check_database_integrity`, `is_corruption`). Es conocimiento de SQLite, no de
Alembic: quien lo usa al arrancar es `persistence/migrations.py`.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path, PurePath
from typing import Any, Final

from sqlalchemy import Engine, event
from sqlalchemy.pool import Pool, StaticPool
from sqlmodel import Session, SQLModel, create_engine

# El import registra las diez tablas en SQLModel.metadata. No es decorativo:
# sin el, create_all no crea nada y los mappers no se pueden configurar.
from backend.app.infrastructure.persistence import models as _models  # noqa: F401

logger = logging.getLogger("led_room.persistence")

#: URL de una base efimera en memoria, para tests.
IN_MEMORY_URL = "sqlite://"

#: Textos de SQLite que significan "el archivo existe pero no es una base
#: utilizable". No hay codigo de error estable en `sqlite3` para distinguirlos
#: (`sqlite3.DatabaseError` cubre desde SQLITE_CORRUPT hasta SQLITE_NOTADB), asi
#: que se reconocen por el mensaje. Los dos primeros estan verificados contra
#: archivos reales -- el segundo, contra la base del incidente --; los otros dos
#: son las variantes con las que SQLite describe el mismo estado.
_CORRUPTION_MARKERS: Final = (
    "file is not a database",  # SQLITE_NOTADB
    "database disk image is malformed",  # SQLITE_CORRUPT: el del incidente
    "file is encrypted or is not a database",
    "malformed database schema",
)


class DatabaseCorruptedError(RuntimeError):
    """El archivo de base de datos existe pero SQLite no lo puede leer.

    No es un fallo recuperable ni un modo degradado: reintentar no repara un
    archivo corrupto. Quien la reciba debe parar y avisar al operador
    (`persistence/migrations.py`), nunca capturarla y seguir.
    """

    def __init__(self, database: Path, detail: str) -> None:
        super().__init__(f"{database}: {detail}")
        self.database = database
        self.detail = detail


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


def is_corruption(error: BaseException) -> bool:
    """True si `error`, o cualquiera de sus causas, es una corrupcion de SQLite.

    Hay que recorrer la cadena porque el fallo llega envuelto: SQLAlchemy
    encapsula el `sqlite3.DatabaseError` en un `sqlalchemy.exc.DatabaseError`
    (atributo `orig`) y Alembic lo deja pasar tal cual. Comprobar solo la
    excepcion de arriba hace que la deteccion falle exactamente en el caso que
    motivo esta funcion: `PRAGMA main.table_info("alembic_version")` durante el
    `upgrade`.
    """
    return any(
        marker in str(current).lower()
        for current in _error_chain(error)
        for marker in _CORRUPTION_MARKERS
    )


def _error_chain(error: BaseException) -> Iterator[BaseException]:
    """La excepcion y todo lo que la envuelve, sin ciclos ni repeticiones."""
    seen: set[int] = set()
    pending: list[BaseException] = [error]

    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current

        for nested in (current.__cause__, current.__context__, getattr(current, "orig", None)):
            if isinstance(nested, BaseException):
                pending.append(nested)


def check_database_integrity(database: Path) -> None:
    """`PRAGMA quick_check` sobre el archivo, ANTES de que nadie lo migre.

    Existe porque una base corrupta se manifiesta hoy como una traza de
    SQLAlchemy dentro de `alembic upgrade head`, y el contenedor la repite en
    cada reinicio sin que el mensaje diga que hacer.

    Tres decisiones:

    * **`quick_check` y no `integrity_check`**: detecta lo mismo salvo la
      coherencia de los indices. Medido sobre bases sanas en modo WAL: 0,7 ms a
      0,15 MiB (el tamano real hoy), 6,8 ms a 4,5 MiB y 67 ms a 45 MiB, frente a
      los ~690 ms que cuesta el `alembic upgrade head` que viene detras. No hace
      falta condicionarlo.
    * **Solo lectura** (`mode=ro`): abrir en escritura una base sospechosa
      dispara la recuperacion del journal, que es escritura sobre el unico
      archivo que el usuario quiza quiera recuperar.
    * **Se abre con `sqlite3`, no con el engine**: el listener de PRAGMA pondria
      `journal_mode=WAL` en el camino de diagnostico.

    Un archivo ausente NO es un error: es el primer arranque, y crearlo es
    trabajo de Alembic.
    """
    # `resolve()` por la misma razon que en `build_database_url`, y ademas
    # porque `as_uri()` exige una ruta absoluta.
    path = Path(database).expanduser().resolve()
    if not path.is_file():
        return

    try:
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
            rows = connection.execute("PRAGMA quick_check").fetchall()
    except sqlite3.DatabaseError as error:
        if is_corruption(error):
            raise DatabaseCorruptedError(path, str(error)) from error
        raise

    problems = [str(row[0]) for row in rows]
    if problems != ["ok"]:
        # `quick_check` tambien puede informar sin lanzar: devuelve una fila por
        # problema encontrado. Se acotan a tres para no volcar un informe entero
        # en el log del contenedor.
        raise DatabaseCorruptedError(path, "; ".join(problems[:3]))


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

            # WAL permite leer mientras se escribe y reduce los bloqueos. Se
            # mantiene SIEMPRE activo, tambien despues del incidente de
            # corrupcion: el modo no es la causa, lo es escribir el mismo
            # archivo desde el host y desde el contenedor a traves de un bind
            # mount virtualizado, y eso se arregla en el volumen, no aqui. No se
            # intenta en memoria, y si el sistema de archivos no lo soporta se
            # degrada al journal por defecto en vez de impedir el arranque.
            if engine.url.database not in (None, ":memory:"):
                try:
                    _enable_wal(cursor)
                except sqlite3.Error:
                    logger.warning(
                        "No se pudo activar WAL; se continua con el journal por defecto",
                        exc_info=True,
                    )

            # Espera en vez de fallar de inmediato si otra conexion escribe.
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


def _enable_wal(cursor: sqlite3.Cursor) -> None:
    """Activa WAL y COMPRUEBA que SQLite lo acepto de verdad.

    `PRAGMA journal_mode` no lanza cuando el sistema de archivos no soporta la
    memoria compartida que WAL necesita: devuelve el modo que quedo puesto. Sin
    leer esa fila, el `except` de arriba casi nunca se dispara y el proyecto
    creeria estar en WAL sobre montajes donde no lo esta. El aviso no cambia el
    comportamiento -- el journal por defecto es correcto, solo mas lento con
    lecturas concurrentes -- pero deja el dato en el log del arranque.
    """
    row = cursor.execute("PRAGMA journal_mode=WAL").fetchone()
    mode = str(row[0]).lower() if row else "desconocido"
    if mode != "wal":
        logger.warning(
            "SQLite no acepto WAL; journal_mode efectivo = %s. "
            "Es lo esperado en montajes de red o bind mounts virtualizados",
            mode,
        )
    cursor.execute("PRAGMA synchronous=NORMAL")


def create_all(engine: Engine) -> None:
    """Crea el esquema sin Alembic.

    Solo para tests y bases efimeras. En el despliegue real manda Alembic
    (LED_ROOM_DATABASE_MODEL 47).
    """
    SQLModel.metadata.create_all(engine)


def session_factory(engine: Engine) -> Iterator[Session]:
    """Dependencia de FastAPI: `Depends(...)` sobre un generador SINCRONO.

    Al no ser `async`, Starlette ejecuta en el threadpool **abrir y cerrar** la
    sesion. Las consultas no: esas las hace la ruta, que si es `async`, y sacarlas
    del bucle de eventos es responsabilidad suya (`run_in_threadpool`).
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
