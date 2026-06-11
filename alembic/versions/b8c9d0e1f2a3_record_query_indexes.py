"""record query indexes for gantt and filters

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-10

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_project_records_estado",
        "project_records",
        ["project_id", "record_type", "estado"],
    )
    op.create_index(
        "idx_project_records_fechas",
        "project_records",
        ["project_id", "fecha_inicio", "fecha_fin"],
    )


def downgrade() -> None:
    op.drop_index("idx_project_records_fechas", table_name="project_records")
    op.drop_index("idx_project_records_estado", table_name="project_records")
