"""hub_entries refactor: visible_roles, record_id, nuevos tipos, drop visibilidad

Revision ID: a2b3c4d5e6f7
Revises: z6a7b8c9d0e1
Create Date: 2026-06-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "z6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    cols = inspect(op.get_bind()).get_columns(table)
    return any(c["name"] == column for c in cols)


def upgrade() -> None:
    # Guard against partial previous runs (SQLite DDL is non-transactional)
    if not _has_column("hub_entries", "visible_roles"):
        op.add_column(
            "hub_entries",
            sa.Column("visible_roles", sa.JSON(), nullable=False, server_default="[]"),
        )
    if not _has_column("hub_entries", "record_id"):
        op.add_column(
            "hub_entries",
            sa.Column("record_id", sa.Uuid(as_uuid=True), nullable=True),
        )

    # Batch recreation needed for: FK, constraint drops/adds, and drop column
    with op.batch_alter_table("hub_entries") as batch_op:
        batch_op.create_foreign_key(
            "fk_hub_entries_record_id",
            "project_records",
            ["record_id"],
            ["id"],
            ondelete="SET NULL",
        )
        try:
            batch_op.drop_constraint("chk_hub_entry_visibilidad", type_="check")
        except Exception:
            pass
        if _has_column("hub_entries", "visibilidad"):
            batch_op.drop_column("visibilidad")
        try:
            batch_op.drop_constraint("chk_hub_entry_tipo", type_="check")
        except Exception:
            pass
        batch_op.create_check_constraint(
            "chk_hub_entry_tipo",
            "tipo IN ('update', 'note', 'shortcut', 'page', 'canvas')",
        )


def downgrade() -> None:
    with op.batch_alter_table("hub_entries") as batch_op:
        try:
            batch_op.drop_constraint("chk_hub_entry_tipo", type_="check")
        except Exception:
            pass
        batch_op.create_check_constraint(
            "chk_hub_entry_tipo",
            "tipo IN ('update', 'note')",
        )
        if not _has_column("hub_entries", "visibilidad"):
            batch_op.add_column(
                sa.Column(
                    "visibilidad",
                    sa.String(length=10),
                    nullable=False,
                    server_default="publico",
                )
            )
        batch_op.create_check_constraint(
            "chk_hub_entry_visibilidad",
            "visibilidad IN ('publico', 'interno')",
        )
        try:
            batch_op.drop_constraint("fk_hub_entries_record_id", type_="foreignkey")
        except Exception:
            pass
        batch_op.drop_column("record_id")
        batch_op.drop_column("visible_roles")
