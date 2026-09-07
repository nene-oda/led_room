"""unique device transport identity

Revision ID: 4f017943d746
Revises: 68a5fc9fc7d4
Create Date: 2026-09-06

Un mismo controlador fisico no puede estar registrado dos veces. Sin esto,
`get_by_address` y el `upsert` del repositorio de dispositivos son ambiguos en
cuanto dos escaneos registren la misma direccion (NEXT_STEPS 4.5).

Migracion nueva en vez de regenerar el baseline: ya existen bases con la
revision 68a5fc9fc7d4 aplicada (el host de desarrollo y cualquier volumen de
contenedor). Reescribir 0001 las dejaria para siempre sin este indice mientras
Alembic las declara al dia, que es exactamente la divergencia silenciosa que
ARCHITECTURE 7.5 describe.

`CREATE UNIQUE INDEX` es nativo en SQLite, asi que no hace falta el modo batch
ni recrear la tabla, con las claves foraneas de `device_capabilities`,
`device_state` y `scene_targets` apuntando a `devices`.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "4f017943d746"
down_revision: str | Sequence[str] | None = "68a5fc9fc7d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_devices_adapter_type_ble_address"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "devices",
        ["adapter_type", "ble_address"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="devices")
