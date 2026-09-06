"""Entorno de Alembic para LED Room.

Dos decisiones que conviene no deshacer:

1. La URL NO se lee de alembic.ini, sino de la misma `Settings` que usa la
   aplicacion. Asi `LED_ROOM_DATABASE` es la unica fuente de verdad y la
   migracion no puede apuntar a un archivo distinto del que abre el backend.
2. `render_as_batch=True`. SQLite carece de casi todo `ALTER TABLE`: sin el
   modo batch, cualquier migracion futura que cambie un tipo, añada un CHECK o
   borre una columna fallaria. Con el, Alembic recrea la tabla y copia los
   datos.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlmodel import SQLModel

from alembic import context
from backend.app.config import get_settings

# El import registra las diez tablas en SQLModel.metadata. Sin el, autogenerate
# creeria que la base sobra entera y generaria un drop_table por tabla.
from backend.app.infrastructure.persistence import models  # noqa: F401
from backend.app.infrastructure.persistence.database import build_database_url
from backend.app.infrastructure.persistence.models.base import UtcDateTime

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _database_url() -> str:
    """URL efectiva, por orden de precedencia.

    1. `alembic -x url=sqlite:///...` (tests y diagnostico).
    2. `sqlalchemy.url` puesto por codigo (ver `persistence/migrations.py`).
    3. `LED_ROOM_DATABASE`, que es la fuente de verdad del despliegue.

    El alembic.ini NO trae `sqlalchemy.url`: si lo trajera, un despiste dejaria
    la migracion escribiendo en un archivo distinto del que abre FastAPI.
    """
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return str(override)

    from_config = config.get_main_option("sqlalchemy.url", None)
    if from_config:
        return from_config

    return build_database_url(get_settings().database)


def _render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Renderiza los tipos propios como tipos estandar de SQLAlchemy.

    Sin esto, autogenerate escribe
    `backend.app.infrastructure.persistence.models.base.UtcDateTime()` en la
    migracion sin importar el modulo: el archivo generado ni siquiera compila.
    Y aunque se importara, una migracion aplicada quedaria atada para siempre a
    la ruta de un modulo de la aplicacion. Una migracion debe describir DDL, no
    depender del dominio.
    """
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime()"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
        render_item=_render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy.pool import NullPool

    from backend.app.infrastructure.persistence.database import create_database_engine

    # Reutiliza el engine de la aplicacion: mismos connect_args, mismos PRAGMA
    # (foreign_keys=ON incluido) y el directorio se crea si no existe.
    connectable = create_database_engine(url=_database_url(), poolclass=NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            render_item=_render_item,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
