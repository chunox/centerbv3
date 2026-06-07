"""feature_queries table

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-06-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h8c9d0e1f2a3"
down_revision: Union[str, None] = "g7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feature_queries",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("feature_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("estado", sa.String(length=30), nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["features.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_feature_queries_feature", "feature_queries", ["feature_id"]
    )
    op.create_index("idx_feature_queries_estado", "feature_queries", ["estado"])


def downgrade() -> None:
    op.drop_index("idx_feature_queries_estado", table_name="feature_queries")
    op.drop_index("idx_feature_queries_feature", table_name="feature_queries")
    op.drop_table("feature_queries")
