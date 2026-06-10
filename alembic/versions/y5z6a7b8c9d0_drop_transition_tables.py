"""drop legacy state transition tables

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
Create Date: 2026-06-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y5z6a7b8c9d0"
down_revision: Union[str, None] = "x4y5z6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("task_state_transitions")
    op.drop_table("feature_state_transitions")


def downgrade() -> None:
    op.create_table(
        "feature_state_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tipo_proyecto", sa.String(length=20), nullable=False),
        sa.Column("estado_desde", sa.String(length=40), nullable=False),
        sa.Column("estado_hasta", sa.String(length=40), nullable=False),
        sa.Column("rol_permitido", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tipo_proyecto",
            "estado_desde",
            "estado_hasta",
            "rol_permitido",
            name="uq_feature_transition",
        ),
    )
    op.create_table(
        "task_state_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("estado_desde", sa.String(length=20), nullable=False),
        sa.Column("estado_hasta", sa.String(length=20), nullable=False),
        sa.Column("rol_permitido", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "estado_desde",
            "estado_hasta",
            "rol_permitido",
            name="uq_task_transition",
        ),
    )
