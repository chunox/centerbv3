"""notifications table

Revision ID: m3b4c5d6e7f8
Revises: l2a3b4c5d6e7
Create Date: 2026-06-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m3b4c5d6e7f8"
down_revision: Union[str, None] = "l2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("entidad_tipo", sa.String(length=20), nullable=False),
        sa.Column("entidad_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("leida", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_notifications_user", "notifications", ["user_id", "leida"]
    )
    op.create_index("idx_notifications_project", "notifications", ["project_id"])
    op.create_index(
        "idx_notifications_entidad",
        "notifications",
        ["entidad_tipo", "entidad_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_notifications_entidad", table_name="notifications")
    op.drop_index("idx_notifications_project", table_name="notifications")
    op.drop_index("idx_notifications_user", table_name="notifications")
    op.drop_table("notifications")
