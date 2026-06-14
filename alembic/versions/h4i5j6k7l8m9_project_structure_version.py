"""add projects.structure_version

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-06-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h4i5j6k7l8m9"
down_revision: Union[str, None] = "g3h4i5j6k7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("projects") as batch:
            batch.add_column(
                sa.Column("structure_version", sa.Integer(), nullable=False, server_default="2")
            )
    else:
        op.add_column(
            "projects",
            sa.Column("structure_version", sa.Integer(), nullable=False, server_default="2"),
        )


def downgrade() -> None:
    op.drop_column("projects", "structure_version")
