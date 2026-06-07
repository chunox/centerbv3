"""feature_reports table and features.origen_report FK

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feature_reports",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("feature_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("reported_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("generated_feature_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["features.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reported_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["generated_feature_id"], ["features.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_feature_reports_feature", "feature_reports", ["feature_id"]
    )
    op.create_index("idx_feature_reports_estado", "feature_reports", ["estado"])
    op.create_index(
        "idx_feature_reports_generated",
        "feature_reports",
        ["generated_feature_id"],
    )

    with op.batch_alter_table("features", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_features_origen_report",
            "feature_reports",
            ["origen_report_id"],
            ["id"],
        )
    op.create_index(
        "idx_features_origen_report", "features", ["origen_report_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_features_origen_report", table_name="features")
    with op.batch_alter_table("features", schema=None) as batch_op:
        batch_op.drop_constraint("fk_features_origen_report", type_="foreignkey")
    op.drop_index("idx_feature_reports_generated", table_name="feature_reports")
    op.drop_index("idx_feature_reports_estado", table_name="feature_reports")
    op.drop_index("idx_feature_reports_feature", table_name="feature_reports")
    op.drop_table("feature_reports")
