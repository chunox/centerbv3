"""drop project_record_types.storage (always 'generic', never used for routing)

Revision ID: k2l3m4n5o6p7
Revises: j6k7l8m9n0o1
Create Date: 2026-06-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k2l3m4n5o6p7"
down_revision: Union[str, None] = "j6k7l8m9n0o1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("project_record_types") as batch_op:
            batch_op.drop_column("storage")
    else:
        op.drop_column("project_record_types", "storage")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("project_record_types") as batch_op:
            batch_op.add_column(
                sa.Column("storage", sa.String(10), nullable=False, server_default="generic")
            )
    else:
        op.add_column(
            "project_record_types",
            sa.Column("storage", sa.String(10), nullable=False, server_default="generic"),
        )
