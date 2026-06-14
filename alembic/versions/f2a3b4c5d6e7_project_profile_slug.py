"""add projects.profile_slug and backfill from tipo

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("profile_slug", sa.String(length=40), nullable=False, server_default="default"),
    )
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.execute(
            sa.text(
                """
                UPDATE projects SET profile_slug = 'with_client' WHERE tipo = 'con_cliente'
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE projects SET profile_slug = 'internal' WHERE tipo = 'interno'
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE projects SET profile_slug = 'flexible'
                WHERE tipo = 'freestyle' AND pack_slug = 'software'
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE projects SET profile_slug = 'default'
                WHERE tipo = 'freestyle' AND pack_slug != 'software'
                """
            )
        )
    else:
        op.execute("UPDATE projects SET profile_slug = 'with_client' WHERE tipo = 'con_cliente'")
        op.execute("UPDATE projects SET profile_slug = 'internal' WHERE tipo = 'interno'")
        op.execute(
            "UPDATE projects SET profile_slug = 'flexible' "
            "WHERE tipo = 'freestyle' AND pack_slug = 'software'"
        )
        op.execute(
            "UPDATE projects SET profile_slug = 'default' "
            "WHERE tipo = 'freestyle' AND pack_slug != 'software'"
        )


def downgrade() -> None:
    op.drop_column("projects", "profile_slug")
