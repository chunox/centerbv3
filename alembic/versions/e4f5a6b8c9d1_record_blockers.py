"""project_record_blockers — bloqueantes externos de entidades Scrum

Revision ID: e4f5a6b8c9d1
Revises: d3e4f5a6b7c8
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b8c9d1"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_record_blockers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "record_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("project_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column(
            "resolved_by",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_record_blockers_record_id", "project_record_blockers", ["record_id"])
    op.create_index("ix_record_blockers_project_id", "project_record_blockers", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_record_blockers_project_id", table_name="project_record_blockers")
    op.drop_index("ix_record_blockers_record_id", table_name="project_record_blockers")
    op.drop_table("project_record_blockers")
