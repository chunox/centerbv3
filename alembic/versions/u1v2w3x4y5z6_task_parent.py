"""tasks parent_task_id for sub-tasks

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-06-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("tasks")}
    indexes = {idx["name"] for idx in insp.get_indexes("tasks")}

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        if "parent_task_id" not in cols:
            batch_op.add_column(
                sa.Column("parent_task_id", sa.Uuid(as_uuid=True), nullable=True),
            )
        if "idx_tasks_parent" not in indexes:
            batch_op.create_index("idx_tasks_parent", ["parent_task_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_tasks_parent_task",
            "tasks",
            ["parent_task_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_constraint("fk_tasks_parent_task", type_="foreignkey")
        batch_op.drop_index("idx_tasks_parent")
        batch_op.drop_column("parent_task_id")
