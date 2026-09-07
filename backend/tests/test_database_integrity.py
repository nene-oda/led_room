"""Una base de datos corrupta debe pararse en seco y explicarse, no repetirse.

Regresion del incidente del 6 de septiembre: `data/led-room.db` quedo con
`database disk image is malformed` (SQLite en WAL sobre un bind mount de Docker
Desktop en Windows, ademas de un `alembic upgrade head` nativo contra el mismo
archivo con el contenedor abierto encima). El sintoma no fue la corrupcion, sino
lo que el contenedor hizo con ella: 90 minutos reiniciandose cada 60 segundos y
volcando la misma traza de SQLAlchemy, que no dice ni el archivo afectado ni que
hacer con el.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy.exc import DatabaseError as SQLAlchemyDatabaseError

from alembic import command
from backend.app.config import Settings
from backend.app.infrastructure.persistence import migrations
from backend.app.infrastructure.persistence.database import (
    DatabaseCorruptedError,
    check_database_integrity,
    create_database_engine,
    is_corruption,
)

#: Tamano de pagina por defecto de SQLite. Machacar la pagina 3 deja intacta la
#: cabecera (pagina 1), que es justo el caso peligroso: el archivo sigue
#: pareciendo una base de datos y solo se descubre al leer el contenido.
PAGE_SIZE = 4096

#: El mensaje exacto que devolvio SQLite en el incidente.
MALFORMED = "database disk image is malformed"


def _write_healthy_database(path: Path) -> None:
    """Una base en WAL con varias paginas de datos, como la real."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE cosas (id INTEGER PRIMARY KEY, valor TEXT)")
        connection.executemany(
            "INSERT INTO cosas (valor) VALUES (?)",
            [("x" * 200,) for _ in range(500)],
        )
        connection.commit()
        # Sin el checkpoint los datos viven en el -wal y el archivo principal se
        # queda casi vacio: no habria paginas que corromper.
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


@pytest.fixture
def base_sana(tmp_path: Path) -> Path:
    path = tmp_path / "led-room.db"
    _write_healthy_database(path)
    return path


@pytest.fixture
def base_corrupta(base_sana: Path) -> Path:
    contenido = bytearray(base_sana.read_bytes())
    assert len(contenido) > PAGE_SIZE * 3, "La base de prueba necesita varias paginas"
    contenido[PAGE_SIZE * 2 : PAGE_SIZE * 2 + 900] = b"\x00\xff" * 450
    base_sana.write_bytes(bytes(contenido))
    return base_sana


@pytest.fixture
def settings_corruptos(base_corrupta: Path) -> Settings:
    return Settings(database=base_corrupta)


@pytest.fixture
def alembic_nunca_llamado(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Control negativo: si Alembic llega a ejecutarse, el test falla.

    Lo que se comprueba es el ORDEN. Alembic sobre una base corrupta ya falla
    solo; lo que no hacia es fallar ANTES, con un mensaje util.
    """

    def _explotar(*args: object, **kwargs: object) -> None:
        raise AssertionError("Alembic no debe tocar una base que no ha pasado quick_check")

    monkeypatch.setattr(command, "upgrade", _explotar)
    yield


# --------------------------------------------------------------------------- #
# La comprobacion de integridad
# --------------------------------------------------------------------------- #


def test_una_base_sana_pasa_la_comprobacion(base_sana: Path) -> None:
    check_database_integrity(base_sana)


def test_una_base_que_todavia_no_existe_no_es_un_error(tmp_path: Path) -> None:
    """Primer arranque con el volumen vacio: crear el archivo es cosa de Alembic."""
    check_database_integrity(tmp_path / "no-existe-todavia.db")


def test_un_archivo_vacio_no_es_un_error(tmp_path: Path) -> None:
    """Un .db de 0 bytes es una base valida sin tablas, no una base rota."""
    path = tmp_path / "led-room.db"
    path.write_bytes(b"")
    check_database_integrity(path)


def test_una_base_corrupta_se_detecta_con_el_error_del_incidente(base_corrupta: Path) -> None:
    with pytest.raises(DatabaseCorruptedError) as excinfo:
        check_database_integrity(base_corrupta)

    assert excinfo.value.database == base_corrupta.resolve()
    assert MALFORMED in excinfo.value.detail


def test_un_archivo_que_no_es_una_base_de_datos_se_detecta(tmp_path: Path) -> None:
    path = tmp_path / "led-room.db"
    path.write_bytes(b"esto no es una base de datos" * 40)

    with pytest.raises(DatabaseCorruptedError) as excinfo:
        check_database_integrity(path)

    assert "not a database" in excinfo.value.detail


def test_la_comprobacion_no_modifica_el_archivo(base_corrupta: Path) -> None:
    """Se abre en modo lectura: el archivo puede ser lo unico recuperable.

    En escritura, SQLite intentaria recuperar el journal antes de responder, y
    eso es escribir sobre la unica copia que le queda al usuario.
    """
    antes = hashlib.sha256(base_corrupta.read_bytes()).hexdigest()

    with pytest.raises(DatabaseCorruptedError):
        check_database_integrity(base_corrupta)

    assert hashlib.sha256(base_corrupta.read_bytes()).hexdigest() == antes


def test_quick_check_que_informa_sin_lanzar_tambien_para_el_arranque(
    base_sana: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`quick_check` no siempre lanza: puede devolver una fila por problema.

    Se simula con un doble porque provocar ese caso exacto exige fabricar una
    corrupcion de indice, que depende de la version de SQLite y no seria un test
    estable.
    """

    class _ConexionQueInforma:
        def execute(self, sql: str) -> _ConexionQueInforma:
            return self

        def fetchall(self) -> list[tuple[str]]:
            return [("row 5 missing from index ix_devices_name",), ("wrong # of entries",)]

        def close(self) -> None:
            return None

    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: _ConexionQueInforma())

    with pytest.raises(DatabaseCorruptedError) as excinfo:
        check_database_integrity(base_sana)

    assert "missing from index" in excinfo.value.detail


def test_un_error_de_sqlite_que_no_es_corrupcion_sube_tal_cual(
    base_sana: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo de E/S no es corrupcion y NO debe disfrazarse de irrecuperable."""

    def _fallar(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(sqlite3, "connect", _fallar)

    with pytest.raises(sqlite3.OperationalError) as excinfo:
        check_database_integrity(base_sana)

    assert type(excinfo.value) is sqlite3.OperationalError


# --------------------------------------------------------------------------- #
# Reconocer la corrupcion venga envuelta como venga
# --------------------------------------------------------------------------- #


def test_is_corruption_reconoce_el_error_envuelto_por_sqlalchemy() -> None:
    """Tal y como llego en el incidente: dentro de un `sqlalchemy.exc.DatabaseError`."""
    envuelto = SQLAlchemyDatabaseError(
        'PRAGMA main.table_info("alembic_version")',
        None,
        sqlite3.DatabaseError(MALFORMED),
    )

    assert is_corruption(envuelto)


def test_is_corruption_reconoce_una_causa_encadenada() -> None:
    try:
        try:
            raise sqlite3.DatabaseError(MALFORMED)
        except sqlite3.DatabaseError as original:
            raise RuntimeError("fallo al migrar") from original
    except RuntimeError as error:
        assert is_corruption(error)


@pytest.mark.parametrize(
    "error",
    [
        sqlite3.OperationalError("unable to open database file"),
        sqlite3.OperationalError("database is locked"),
        ValueError("rango invalido"),
    ],
    ids=["no-se-puede-abrir", "cerrojo-ocupado", "otro-error"],
)
def test_is_corruption_no_confunde_otros_fallos(error: Exception) -> None:
    """Reintentar SI tiene sentido en estos: no deben acabar en un 78."""
    assert not is_corruption(error)


# --------------------------------------------------------------------------- #
# La migracion
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("alembic_nunca_llamado")
def test_upgrade_to_head_para_antes_de_llamar_a_alembic(settings_corruptos: Settings) -> None:
    with pytest.raises(DatabaseCorruptedError):
        migrations.upgrade_to_head(settings_corruptos)


def test_upgrade_to_head_traduce_una_corrupcion_aparecida_durante_la_migracion(
    base_sana: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`quick_check` no lee todas las paginas: la corrupcion puede salir despues."""

    def _fallar(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyDatabaseError("SELECT 1", None, sqlite3.DatabaseError(MALFORMED))

    monkeypatch.setattr(command, "upgrade", _fallar)

    with pytest.raises(DatabaseCorruptedError):
        migrations.upgrade_to_head(Settings(database=base_sana))


def test_upgrade_to_head_deja_pasar_un_fallo_normal_de_migracion(
    base_sana: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una revision rota debe seguir siendo un 1, no un 78 irrecuperable."""

    def _fallar(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Can't locate revision identified by 'deadbeef'")

    monkeypatch.setattr(command, "upgrade", _fallar)

    with pytest.raises(RuntimeError):
        migrations.upgrade_to_head(Settings(database=base_sana))


# --------------------------------------------------------------------------- #
# El punto de entrada del entrypoint
# --------------------------------------------------------------------------- #


#: Ejecuta `main` contra la base que se le diga: (ruta, argv) -> codigo de salida.
MainRunner = Callable[..., int]


@pytest.fixture
def main_sobre(monkeypatch: pytest.MonkeyPatch) -> MainRunner:
    """Ejecuta `migrations.main` contra una base concreta, NUNCA contra la real.

    `get_settings` esta cacheado con `lru_cache`, asi que se sustituye el nombre
    en el modulo: leer la configuracion de verdad haria que la suite migrara la
    base del desarrollador.
    """

    def _run(database: Path, argv: list[str] | None = None) -> int:
        monkeypatch.setattr(migrations, "get_settings", lambda: Settings(database=database))
        return migrations.main(argv or [])

    return _run


@pytest.mark.usefixtures("alembic_nunca_llamado")
def test_main_devuelve_78_ante_una_base_corrupta(
    base_corrupta: Path,
    main_sobre: MainRunner,
) -> None:
    """78 = EX_CONFIG: arregla los datos, NO reintentes. Ni 75 ni 1."""
    assert main_sobre(base_corrupta) == migrations.EXIT_DATA_CORRUPTED
    assert migrations.EXIT_DATA_CORRUPTED == 78


@pytest.mark.usefixtures("alembic_nunca_llamado")
def test_main_no_imprime_la_traza_cruda(
    base_corrupta: Path,
    main_sobre: MainRunner,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_sobre(base_corrupta)
    salida = capsys.readouterr().err

    assert "Traceback" not in salida
    assert "sqlalchemy" not in salida.lower()
    assert "Background on this error" not in salida
    assert len(salida.splitlines()) <= 12


@pytest.mark.usefixtures("alembic_nunca_llamado")
def test_el_mensaje_dice_que_paso_por_que_y_que_hacer(
    base_corrupta: Path,
    main_sobre: MainRunner,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_sobre(base_corrupta)
    salida = capsys.readouterr().err

    # Que paso, y sobre que archivo.
    assert str(base_corrupta.resolve()) in salida
    assert MALFORMED in salida
    # Que no hay que hacer.
    assert "NO reintente" in salida
    # La causa probable.
    assert "bind mount" in salida
    # Y los dos caminos de salida: recuperar o empezar de cero, mas la
    # prevencion.
    assert ".recover" in salida
    assert "volumen nombrado" in salida


def test_main_devuelve_cero_con_una_base_sana(
    base_sana: Path,
    main_sobre: MainRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[str] = []
    monkeypatch.setattr(
        command,
        "upgrade",
        lambda config, revision: llamadas.append(revision),
    )

    assert main_sobre(base_sana) == 0
    assert llamadas == ["head"]


def test_main_usa_el_alembic_ini_que_le_pasa_el_entrypoint(
    base_sana: Path,
    main_sobre: MainRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El entrypoint invoca `python -m ... /app/alembic.ini`; el argumento manda."""
    recibido: list[Path | None] = []

    def _config(settings: Settings, ini_path: Path | None = None) -> object:
        recibido.append(ini_path)
        return object()

    monkeypatch.setattr(migrations, "build_alembic_config", _config)
    monkeypatch.setattr(command, "upgrade", lambda config, revision: None)

    assert main_sobre(base_sana, ["/app/alembic.ini"]) == 0
    assert recibido == [Path("/app/alembic.ini")]


# --------------------------------------------------------------------------- #
# WAL
# --------------------------------------------------------------------------- #


def test_una_base_en_archivo_queda_en_modo_wal(tmp_path: Path) -> None:
    """El listener lee ahora la fila que devuelve el PRAGMA; que siga cumpliendose.

    Es el control positivo del aviso: si algun dia este test empieza a fallar en
    un host, es que el aviso de "SQLite no acepto WAL" esta diciendo la verdad.
    """
    engine = create_database_engine(tmp_path / "led-room.db")
    try:
        with engine.connect() as connection:
            modo = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
    finally:
        engine.dispose()

    assert str(modo).lower() == "wal"
