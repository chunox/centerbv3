"""convert Text JSON columns to native JSON/JSONB

Covers: project_record_types.field_schema, parent_types;
        project_workflow_definitions.definition;
        project_workbench_definitions.definition;
        project_communication_rules.definition;
        project_packs.manifest;
        project_config_snapshots.payload

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-06-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l3m4n5o6p7q8"
down_revision: Union[str, None] = "k2l3m4n5o6p7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite stores JSON as TEXT natively; SQLAlchemy's JSON type handles
        # serialization at the ORM layer, so no structural change is needed.
        return

    from sqlalchemy.dialects.postgresql import JSONB

    # project_record_types
    op.execute(
        "ALTER TABLE project_record_types "
        "ALTER COLUMN field_schema TYPE JSONB USING "
        "CASE WHEN field_schema IS NULL OR field_schema = '' "
        "THEN '[]'::jsonb ELSE field_schema::jsonb END"
    )
    op.execute(
        "ALTER TABLE project_record_types "
        "ALTER COLUMN parent_types TYPE JSONB USING "
        "CASE WHEN parent_types IS NULL OR parent_types = '' "
        "THEN NULL ELSE parent_types::jsonb END"
    )

    for table, col, default in [
        ("project_workflow_definitions", "definition", "{}"),
        ("project_workbench_definitions", "definition", "{}"),
        ("project_communication_rules", "definition", "[]"),
        ("project_packs", "manifest", "{}"),
        ("project_config_snapshots", "payload", "{}"),
    ]:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE JSONB "
            f"USING CASE WHEN {col} IS NULL OR {col} = '' "
            f"THEN '{default}'::jsonb ELSE {col}::jsonb END"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, col in [
        ("project_record_types", "field_schema"),
        ("project_record_types", "parent_types"),
        ("project_workflow_definitions", "definition"),
        ("project_workbench_definitions", "definition"),
        ("project_communication_rules", "definition"),
        ("project_packs", "manifest"),
        ("project_config_snapshots", "payload"),
    ]:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TEXT USING {col}::text"
        )
