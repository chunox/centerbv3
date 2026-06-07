"""tasks table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("feature_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("asignado_a", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["features.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["asignado_a"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tasks_feature", "tasks", ["feature_id"])
    op.create_index("idx_tasks_project", "tasks", ["project_id"])
    op.create_index("idx_tasks_assignee", "tasks", ["asignado_a"])
    op.create_index("idx_tasks_status", "tasks", ["estado"])


def downgrade() -> None:
    op.drop_index("idx_tasks_status", table_name="tasks")
    op.drop_index("idx_tasks_assignee", table_name="tasks")
    op.drop_index("idx_tasks_project", table_name="tasks")
    op.drop_index("idx_tasks_feature", table_name="tasks")
    op.drop_table("tasks")
