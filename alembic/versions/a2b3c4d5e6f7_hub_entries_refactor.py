"""hub_entries refactor: visible_roles, record_id, nuevos tipos, drop visibilidad

Revision ID: a2b3c4d5e6f7
Revises: z6a7b8c9d0e1
Create Date: 2026-06-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "z6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add visible_roles — replaces visibilidad varchar
    op.add_column(
        "hub_entries",
        sa.Column("visible_roles", sa.JSON(), nullable=False, server_default="[]"),
    )

    # 2. Add record_id FK — used by shortcut entries
    op.add_column(
        "hub_entries",
        sa.Column("record_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_hub_entries_record_id",
        "hub_entries",
        "project_records",
        ["record_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Drop old visibilidad check constraint then column
    op.drop_constraint("chk_hub_entry_visibilidad", "hub_entries", type_="check")
    op.drop_column("hub_entries", "visibilidad")

    # 4. Expand tipo check constraint to include shortcut, page, canvas
    op.drop_constraint("chk_hub_entry_tipo", "hub_entries", type_="check")
    op.create_check_constraint(
        "chk_hub_entry_tipo",
        "hub_entries",
        "tipo IN ('update', 'note', 'shortcut', 'page', 'canvas')",
    )


def downgrade() -> None:
    # Restore tipo constraint
    op.drop_constraint("chk_hub_entry_tipo", "hub_entries", type_="check")
    op.create_check_constraint(
        "chk_hub_entry_tipo",
        "hub_entries",
        "tipo IN ('update', 'note')",
    )

    # Restore visibilidad column
    op.add_column(
        "hub_entries",
        sa.Column(
            "visibilidad",
            sa.String(length=10),
            nullable=False,
            server_default="publico",
        ),
    )
    op.create_check_constraint(
        "chk_hub_entry_visibilidad",
        "hub_entries",
        "visibilidad IN ('publico', 'interno')",
    )

    # Drop record_id
    op.drop_constraint("fk_hub_entries_record_id", "hub_entries", type_="foreignkey")
    op.drop_column("hub_entries", "record_id")

    # Drop visible_roles
    op.drop_column("hub_entries", "visible_roles")
