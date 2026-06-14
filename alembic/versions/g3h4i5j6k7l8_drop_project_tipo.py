"""drop projects.tipo column (replaced by profile_slug)

Revision ID: g3h4i5j6k7l8
Revises: f2a3b4c5d6e7
Create Date: 2026-06-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g3h4i5j6k7l8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("projects", "tipo")


def downgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("tipo", sa.String(length=20), nullable=False, server_default="con_cliente"),
    )
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.execute(
            sa.text(
                """
                UPDATE projects SET tipo = 'con_cliente' WHERE profile_slug = 'with_client'
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE projects SET tipo = 'interno' WHERE profile_slug IN ('internal', 'default')
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE projects SET tipo = 'freestyle' WHERE profile_slug = 'flexible'
                """
            )
        )
    else:
        op.execute("UPDATE projects SET tipo = 'con_cliente' WHERE profile_slug = 'with_client'")
        op.execute(
            "UPDATE projects SET tipo = 'interno' WHERE profile_slug IN ('internal', 'default')"
        )
        op.execute("UPDATE projects SET tipo = 'freestyle' WHERE profile_slug = 'flexible'")
