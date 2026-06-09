"""task_dependencies table

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-06-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t0u1v2w3x4y5"
down_revision: Union[str, None] = "s9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("depends_on_task_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_task_id"], ["tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "depends_on_task_id"),
        sa.CheckConstraint("task_id <> depends_on_task_id"),
    )
    op.create_index("idx_task_deps_task", "task_dependencies", ["task_id"])
    op.create_index(
        "idx_task_deps_depends", "task_dependencies", ["depends_on_task_id"]
    )
    op.create_index("idx_task_deps_project", "task_dependencies", ["project_id"])


def downgrade() -> None:
    op.drop_index("idx_task_deps_project", table_name="task_dependencies")
    op.drop_index("idx_task_deps_depends", table_name="task_dependencies")
    op.drop_index("idx_task_deps_task", table_name="task_dependencies")
    op.drop_table("task_dependencies")
