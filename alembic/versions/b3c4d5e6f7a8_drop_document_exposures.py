"""drop document_exposures table

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-06-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("document_exposures")


def downgrade() -> None:
    op.create_table(
        "document_exposures",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ambito", sa.String(20), nullable=False),
        sa.Column(
            "record_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("project_records.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "attachment_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("attachments.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "hub_entry_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("hub_entries.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("titulo_visible", sa.String(255), nullable=True),
        sa.Column(
            "expuesto_por",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(document_id IS NOT NULL AND attachment_id IS NULL AND hub_entry_id IS NULL) "
            "OR (document_id IS NULL AND attachment_id IS NOT NULL AND hub_entry_id IS NULL) "
            "OR (document_id IS NULL AND attachment_id IS NULL AND hub_entry_id IS NOT NULL)",
            name="chk_exposure_target",
        ),
        sa.CheckConstraint(
            "(ambito = 'proyecto' AND record_id IS NULL) "
            "OR (ambito IN ('milestone', 'feature', 'record') AND record_id IS NOT NULL)",
            name="chk_exposure_ambito",
        ),
    )
