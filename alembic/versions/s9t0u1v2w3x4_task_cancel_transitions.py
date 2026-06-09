"""task cancel transitions — cancelación individual por Dev

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-06-09

"""

from datetime import datetime
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "s9t0u1v2w3x4"
down_revision: Union[str, None] = "r8s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TASK_CANCEL_TRANSITIONS = [
    ("backlog", "cancel", "dev"),
    ("to_do", "cancel", "dev"),
    ("in_progress", "cancel", "dev"),
    ("ready_for_test", "cancel", "dev"),
]


def upgrade() -> None:
    task_table = sa.table(
        "task_state_transitions",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("estado_desde", sa.String()),
        sa.column("estado_hasta", sa.String()),
        sa.column("rol_permitido", sa.String()),
        sa.column("created_at", sa.DateTime()),
    )
    now = datetime.utcnow()
    conn = op.get_bind()
    for desde, hasta, rol in _TASK_CANCEL_TRANSITIONS:
        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM task_state_transitions "
                "WHERE estado_desde = :desde AND estado_hasta = :hasta "
                "AND rol_permitido = :rol"
            ),
            {"desde": desde, "hasta": hasta, "rol": rol},
        ).first()
        if exists:
            continue
        op.execute(
            task_table.insert().values(
                id=uuid.uuid4(),
                estado_desde=desde,
                estado_hasta=hasta,
                rol_permitido=rol,
                created_at=now,
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    for desde, hasta, rol in _TASK_CANCEL_TRANSITIONS:
        conn.execute(
            sa.text(
                "DELETE FROM task_state_transitions "
                "WHERE estado_desde = :desde AND estado_hasta = :hasta "
                "AND rol_permitido = :rol"
            ),
            {"desde": desde, "hasta": hasta, "rol": rol},
        )
