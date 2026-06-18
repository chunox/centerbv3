"""Add Scrum ceremony sessions and entries tables

Revision ID: c2d3e4f5a6b7
Revises: 1b15e65662a5
Create Date: 2026-06-17 23:05:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "1b15e65662a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scrum_ceremony_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("sprint_id", sa.Uuid(), nullable=True),
        sa.Column("session_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("facilitator_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "session_type IN ('daily', 'planning_poker', 'sprint_review', 'retro')",
            name="chk_scrum_session_type",
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'active', 'closed')",
            name="chk_scrum_session_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sprint_id"], ["project_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["facilitator_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scrum_ceremony_sessions_project_type",
        "scrum_ceremony_sessions",
        ["project_id", "session_type"],
    )
    op.create_index(
        "ix_scrum_ceremony_sessions_project_status",
        "scrum_ceremony_sessions",
        ["project_id", "status"],
    )

    op.create_table(
        "scrum_ceremony_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["scrum_ceremony_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scrum_ceremony_entries_session_created",
        "scrum_ceremony_entries",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scrum_ceremony_entries_session_created",
        table_name="scrum_ceremony_entries",
    )
    op.drop_table("scrum_ceremony_entries")
    op.drop_index(
        "ix_scrum_ceremony_sessions_project_status",
        table_name="scrum_ceremony_sessions",
    )
    op.drop_index(
        "ix_scrum_ceremony_sessions_project_type",
        table_name="scrum_ceremony_sessions",
    )
    op.drop_table("scrum_ceremony_sessions")
