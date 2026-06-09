"""task_assignees many-to-many; drop tasks.asignado_a

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-06-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v2w3x4y5z6a7"
down_revision: Union[str, None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "task_assignees" not in tables:
        op.create_table(
            "task_assignees",
            sa.Column("task_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("task_id", "user_id"),
        )
        op.create_index(
            "idx_task_assignees_user", "task_assignees", ["user_id"], unique=False
        )

    cols = {c["name"] for c in insp.get_columns("tasks")}
    if "asignado_a" in cols:
        op.execute(
            sa.text(
                "INSERT OR IGNORE INTO task_assignees (task_id, user_id) "
                "SELECT id, asignado_a FROM tasks WHERE asignado_a IS NOT NULL"
            )
        )

        indexes = {idx["name"] for idx in insp.get_indexes("tasks")}
        with op.batch_alter_table("tasks", schema=None) as batch_op:
            if "idx_tasks_assignee" in indexes:
                batch_op.drop_index("idx_tasks_assignee")
            batch_op.drop_column("asignado_a")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("tasks")}

    if "asignado_a" not in cols:
        with op.batch_alter_table("tasks", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("asignado_a", sa.Uuid(as_uuid=True), nullable=True),
            )
            batch_op.create_index("idx_tasks_assignee", ["asignado_a"], unique=False)
            batch_op.create_foreign_key(
                "fk_tasks_asignado_a_users",
                "users",
                ["asignado_a"],
                ["id"],
            )

    tables = set(insp.get_table_names())
    if "task_assignees" in tables:
        op.execute(
            sa.text(
                "UPDATE tasks SET asignado_a = ("
                "SELECT user_id FROM task_assignees ta "
                "WHERE ta.task_id = tasks.id LIMIT 1"
                ")"
            )
        )
        op.drop_index("idx_task_assignees_user", table_name="task_assignees")
        op.drop_table("task_assignees")
