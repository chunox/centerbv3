"""backfill milestone workflow for existing projects

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
Create Date: 2026-06-09

"""

from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x4y5z6a7b8c9"
down_revision: Union[str, None] = "w3x4y5z6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.domain.workflow_templates import workflow_for_project_tipo

    conn = op.get_bind()
    projects = conn.execute(sa.text("SELECT id, tipo FROM projects")).fetchall()
    for project_id, tipo in projects:
        has_milestone = conn.execute(
            sa.text(
                """
                SELECT 1 FROM project_workflow_definitions
                WHERE project_id = :pid AND entity_type = 'milestone' LIMIT 1
                """
            ),
            {"pid": str(project_id)},
        ).fetchone()
        if has_milestone:
            continue
        wf = workflow_for_project_tipo(tipo, "milestone")
        conn.execute(
            sa.text(
                """
                INSERT INTO project_workflow_definitions
                (id, project_id, entity_type, version, is_active, definition, created_at)
                VALUES (:id, :project_id, 'milestone', 1, 1, :definition, datetime('now'))
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "project_id": str(project_id),
                "definition": json.dumps(wf, ensure_ascii=False),
            },
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM project_workflow_definitions WHERE entity_type = 'milestone'"
        )
    )
