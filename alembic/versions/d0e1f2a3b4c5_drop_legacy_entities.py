"""drop legacy entity tables (milestones, features, tasks, etc.)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-11

"""

from typing import Sequence, Union

from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        for table in (
            "task_dependencies",
            "task_assignees",
            "tasks",
            "feature_queries",
            "feature_reports",
            "features",
            "milestones",
        ):
            try:
                op.drop_table(table)
            except Exception:
                pass
    else:
        op.drop_table("task_dependencies")
        op.drop_table("task_assignees")
        op.drop_table("tasks")
        op.drop_table("feature_queries")
        op.drop_table("feature_reports")
        op.drop_table("features")
        op.drop_table("milestones")


def downgrade() -> None:
    pass
