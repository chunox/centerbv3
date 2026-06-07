"""audit_logs table

Revision ID: l2a3b4c5d6e7
Revises: k1f2a3b4c5d6
Create Date: 2026-06-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l2a3b4c5d6e7"
down_revision: Union[str, None] = "k1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entidad_tipo", sa.String(length=20), nullable=False),
        sa.Column("entidad_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("accion", sa.String(length=30), nullable=False),
        sa.Column("campo", sa.String(length=100), nullable=True),
        sa.Column("valor_anterior", sa.Text(), nullable=True),
        sa.Column("valor_nuevo", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_logs_project", "audit_logs", ["project_id"])
    op.create_index(
        "idx_audit_logs_entidad", "audit_logs", ["entidad_tipo", "entidad_id"]
    )
    op.create_index("idx_audit_logs_user", "audit_logs", ["user_id"])
    op.create_index("idx_audit_logs_fecha", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_audit_logs_fecha", table_name="audit_logs")
    op.drop_index("idx_audit_logs_user", table_name="audit_logs")
    op.drop_index("idx_audit_logs_entidad", table_name="audit_logs")
    op.drop_index("idx_audit_logs_project", table_name="audit_logs")
    op.drop_table("audit_logs")
