"""document_exposures FKs point to project_records

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        try:
            op.drop_table("document_exposures")
        except Exception:
            pass
    else:
        op.drop_table("document_exposures")

    op.create_table(
        "document_exposures",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("ambito", sa.String(length=20), nullable=False),
        sa.Column("milestone_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("feature_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("attachment_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("hub_entry_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("titulo_visible", sa.String(length=255), nullable=True),
        sa.Column("expuesto_por", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(document_id IS NOT NULL AND attachment_id IS NULL AND hub_entry_id IS NULL) "
            "OR (document_id IS NULL AND attachment_id IS NOT NULL AND hub_entry_id IS NULL) "
            "OR (document_id IS NULL AND attachment_id IS NULL AND hub_entry_id IS NOT NULL)",
            name="chk_exposure_target",
        ),
        sa.CheckConstraint(
            "(ambito = 'proyecto' AND milestone_id IS NULL AND feature_id IS NULL) "
            "OR (ambito = 'milestone' AND milestone_id IS NOT NULL AND feature_id IS NULL) "
            "OR (ambito = 'feature' AND feature_id IS NOT NULL)",
            name="chk_exposure_ambito",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["project_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["project_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["hub_entry_id"], ["hub_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["expuesto_por"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    pass
