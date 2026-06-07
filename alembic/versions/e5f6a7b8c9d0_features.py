"""features table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "features",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("milestone_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("prioridad", sa.String(length=10), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=False),
        sa.Column("duracion_estimada", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(length=40), nullable=False),
        sa.Column("bloqueada", sa.Boolean(), nullable=False),
        sa.Column("origen_report_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["milestones.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "fecha_fin >= fecha_inicio", name="chk_feature_fechas"
        ),
        sa.CheckConstraint(
            "tipo <> 'mejora' OR duracion_estimada IS NOT NULL",
            name="chk_feature_duracion_mejora",
        ),
    )
    op.create_index("idx_features_milestone", "features", ["milestone_id"])
    op.create_index("idx_features_project", "features", ["project_id"])
    op.create_index("idx_features_estado", "features", ["estado"])


def downgrade() -> None:
    op.drop_index("idx_features_estado", table_name="features")
    op.drop_index("idx_features_project", table_name="features")
    op.drop_index("idx_features_milestone", table_name="features")
    op.drop_table("features")
