"""notifications deep_link + project_config_snapshots

Revision ID: j6k7l8m9n0o1
Revises: i5j6k7l8m9n0
Create Date: 2026-06-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "j6k7l8m9n0o1"
down_revision = "i5j6k7l8m9n0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(sa.Column("deep_link", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("message", sa.String(500), nullable=True))

    op.create_table(
        "project_config_snapshots",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_project_config_snapshots_project_kind",
        "project_config_snapshots",
        ["project_id", "kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_config_snapshots_project_kind", "project_config_snapshots")
    op.drop_table("project_config_snapshots")
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_column("message")
        batch_op.drop_column("deep_link")
