"""effect brightness envelope

Revision ID: 9c1d2b7e4a30
Revises: 4f017943d746
Create Date: 2026-09-06

`PULSE` y `BREATH` necesitan una envolvente de brillo -- un suelo y un techo --
y el esquema no tenia donde ponerla: `effect_steps.brightness` es el brillo de
UN vertice, no de la envolvente, y usarlo para las dos cosas dejaria `PULSE`
como un alias exacto de `SMOOTH_CYCLE` con dos pasos del mismo color.

Migracion aditiva y encadenada, nunca una reescritura del baseline: cualquier
base ya sellada con `4f017943d746` quedaria permanentemente sin las columnas
mientras Alembic la declara al dia (ARCHITECTURE 7.5).

Las columnas son NULL-ables a proposito: una fila sin envolvente significa
"usa la del dominio" (0-100), no "usa cero". Los `CHECK` van dentro de un
`batch_alter_table` porque SQLite no sabe añadir una restriccion a una tabla
existente sin recrearla.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c1d2b7e4a30"
down_revision: str | None = "4f017943d746"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("effects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("min_brightness", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("max_brightness", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_effects_min_brightness",
            "min_brightness IS NULL OR (min_brightness >= 0 AND min_brightness <= 100)",
        )
        batch_op.create_check_constraint(
            "ck_effects_max_brightness",
            "max_brightness IS NULL OR (max_brightness >= 0 AND max_brightness <= 100)",
        )


def downgrade() -> None:
    with op.batch_alter_table("effects", schema=None) as batch_op:
        batch_op.drop_constraint("ck_effects_max_brightness", type_="check")
        batch_op.drop_constraint("ck_effects_min_brightness", type_="check")
        batch_op.drop_column("max_brightness")
        batch_op.drop_column("min_brightness")
