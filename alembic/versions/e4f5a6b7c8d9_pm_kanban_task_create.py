"""PM: permitir crear tareas dev (kanban.task.create).

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-19
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CAPABILITY = "kanban.task.create"
ROLE_SLUG = "pm"


def upgrade() -> None:
    bind = op.get_bind()
    role_rows = bind.execute(
        sa.text("SELECT id FROM project_roles WHERE slug = :slug"),
        {"slug": ROLE_SLUG},
    ).fetchall()
    for (role_id,) in role_rows:
        exists = bind.execute(
            sa.text(
                """
                SELECT 1 FROM project_role_capabilities
                WHERE role_id = :role_id AND capability_key = :cap
                LIMIT 1
                """
            ),
            {"role_id": role_id, "cap": CAPABILITY},
        ).fetchone()
        if exists:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO project_role_capabilities (id, role_id, capability_key)
                VALUES (:id, :role_id, :cap)
                """
            ),
            {"id": str(uuid.uuid4()), "role_id": role_id, "cap": CAPABILITY},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM project_role_capabilities
            WHERE capability_key = :cap
              AND role_id IN (SELECT id FROM project_roles WHERE slug = :slug)
            """
        ),
        {"cap": CAPABILITY, "slug": ROLE_SLUG},
    )
