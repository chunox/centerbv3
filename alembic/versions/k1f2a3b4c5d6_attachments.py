"""attachments and attachment_relations tables

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-06-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k1f2a3b4c5d6"
down_revision: Union[str, None] = "j0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("nombre_original", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("tamano_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "attachment_relations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("attachment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entidad_tipo", sa.String(length=20), nullable=False),
        sa.Column("entidad_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_attachment_relations_attachment",
        "attachment_relations",
        ["attachment_id"],
    )
    op.create_index(
        "idx_attachment_relations_entidad",
        "attachment_relations",
        ["entidad_tipo", "entidad_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_attachment_relations_entidad", table_name="attachment_relations"
    )
    op.drop_index(
        "idx_attachment_relations_attachment", table_name="attachment_relations"
    )
    op.drop_table("attachment_relations")
    op.drop_table("attachments")
