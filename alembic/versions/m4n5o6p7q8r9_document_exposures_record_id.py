"""document_exposures: replace milestone_id + feature_id with record_id

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-06-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m4n5o6p7q8r9"
down_revision: Union[str, None] = "l3m4n5o6p7q8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        # Add column via raw SQL (avoids unnamed FK constraint issue in batch mode)
        op.execute(
            "ALTER TABLE document_exposures "
            "ADD COLUMN record_id TEXT REFERENCES project_records(id) ON DELETE CASCADE"
        )
        # Backfill: pick feature_id first (more specific), then milestone_id
        op.execute(
            "UPDATE document_exposures "
            "SET record_id = COALESCE(feature_id, milestone_id) "
            "WHERE feature_id IS NOT NULL OR milestone_id IS NOT NULL"
        )
        # Recreate table dropping old columns + updating check constraint
        with op.batch_alter_table(
            "document_exposures",
            recreate="always",
        ) as batch_op:
            batch_op.drop_column("milestone_id")
            batch_op.drop_column("feature_id")
            batch_op.drop_constraint("chk_exposure_ambito", type_="check")
            batch_op.create_check_constraint(
                "chk_exposure_ambito",
                "(ambito = 'proyecto' AND record_id IS NULL) "
                "OR (ambito IN ('milestone', 'feature', 'record') AND record_id IS NOT NULL)",
            )

    else:
        # PostgreSQL
        op.add_column(
            "document_exposures",
            sa.Column("record_id", sa.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_document_exposures_record_id",
            "document_exposures",
            "project_records",
            ["record_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.execute(
            "UPDATE document_exposures "
            "SET record_id = COALESCE(feature_id, milestone_id) "
            "WHERE feature_id IS NOT NULL OR milestone_id IS NOT NULL"
        )
        op.drop_constraint("chk_exposure_ambito", "document_exposures", type_="check")
        op.drop_column("document_exposures", "milestone_id")
        op.drop_column("document_exposures", "feature_id")
        op.create_check_constraint(
            "chk_exposure_ambito",
            "document_exposures",
            "(ambito = 'proyecto' AND record_id IS NULL) "
            "OR (ambito IN ('milestone', 'feature', 'record') AND record_id IS NOT NULL)",
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE document_exposures ADD COLUMN milestone_id TEXT "
            "REFERENCES project_records(id) ON DELETE CASCADE"
        )
        op.execute(
            "ALTER TABLE document_exposures ADD COLUMN feature_id TEXT "
            "REFERENCES project_records(id) ON DELETE CASCADE"
        )
        with op.batch_alter_table(
            "document_exposures",
            recreate="always",
        ) as batch_op:
            batch_op.drop_column("record_id")
            batch_op.drop_constraint("chk_exposure_ambito", type_="check")
            batch_op.create_check_constraint(
                "chk_exposure_ambito",
                "(ambito = 'proyecto' AND milestone_id IS NULL AND feature_id IS NULL) "
                "OR (ambito = 'milestone' AND milestone_id IS NOT NULL AND feature_id IS NULL) "
                "OR (ambito = 'feature' AND feature_id IS NOT NULL)",
            )
    else:
        op.add_column(
            "document_exposures",
            sa.Column("milestone_id", sa.UUID(as_uuid=True), nullable=True),
        )
        op.add_column(
            "document_exposures",
            sa.Column("feature_id", sa.UUID(as_uuid=True), nullable=True),
        )
        op.drop_constraint(
            "fk_document_exposures_record_id", "document_exposures", type_="foreignkey"
        )
        op.drop_column("document_exposures", "record_id")
        op.drop_constraint("chk_exposure_ambito", "document_exposures", type_="check")
        op.create_check_constraint(
            "chk_exposure_ambito",
            "document_exposures",
            "(ambito = 'proyecto' AND milestone_id IS NULL AND feature_id IS NULL) "
            "OR (ambito = 'milestone' AND milestone_id IS NOT NULL AND feature_id IS NULL) "
            "OR (ambito = 'feature' AND feature_id IS NOT NULL)",
        )
