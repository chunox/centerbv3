"""comments, feature_state_transitions, task_state_transitions + seed

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-06-04

"""

from datetime import datetime
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "i9d0e1f2a3b4"
down_revision: Union[str, None] = "h8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FEATURE_TRANSITIONS = [
    ("ambos", "pendiente", "en_progreso", "dev"),
    ("ambos", "pendiente", "en_progreso", "pm"),
    ("ambos", "en_progreso", "en_qa", "dev"),
    ("ambos", "en_progreso", "en_qa", "pm"),
    ("ambos", "en_qa", "en_progreso", "qa"),
    ("ambos", "en_qa", "esperando_liberacion_pm", "qa"),
    ("ambos", "esperando_liberacion_pm", "en_progreso", "pm"),
    ("con_cliente", "esperando_liberacion_pm", "esperando_validacion_cliente", "pm"),
    ("con_cliente", "esperando_validacion_cliente", "completado", "cliente"),
    ("con_cliente", "esperando_validacion_cliente", "en_progreso", "cliente"),
    ("interno", "esperando_liberacion_pm", "completado", "pm"),
    ("ambos", "pendiente", "cancelado", "pm"),
    ("ambos", "en_progreso", "cancelado", "pm"),
    ("ambos", "en_qa", "cancelado", "pm"),
    ("ambos", "esperando_liberacion_pm", "cancelado", "pm"),
    ("con_cliente", "esperando_validacion_cliente", "cancelado", "pm"),
]

_TASK_TRANSITIONS = [
    ("abierto", "en_desarrollo", "dev"),
    ("abierto", "en_desarrollo", "pm"),
    ("en_desarrollo", "cerrado", "dev"),
    ("en_desarrollo", "cerrado", "pm"),
    ("abierto", "cancelado", "pm"),
    ("en_desarrollo", "cancelado", "pm"),
]


def _seed_rows(
    rows: list[tuple[str, ...]], columns: list[str]
) -> list[dict]:
    now = datetime.utcnow()
    result = []
    for row in rows:
        data = dict(zip(columns, row, strict=True))
        data["id"] = uuid.uuid4()
        data["created_at"] = now
        result.append(data)
    return result


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entidad_tipo", sa.String(length=20), nullable=False),
        sa.Column("entidad_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("estado_momento", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_comments_entidad", "comments", ["entidad_tipo", "entidad_id"]
    )
    op.create_index("idx_comments_user", "comments", ["user_id"])

    op.create_table(
        "feature_state_transitions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tipo_proyecto", sa.String(length=20), nullable=False),
        sa.Column("estado_desde", sa.String(length=40), nullable=False),
        sa.Column("estado_hasta", sa.String(length=40), nullable=False),
        sa.Column("rol_permitido", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tipo_proyecto",
            "estado_desde",
            "estado_hasta",
            "rol_permitido",
            name="uq_feature_transition",
        ),
    )

    op.create_table(
        "task_state_transitions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("estado_desde", sa.String(length=20), nullable=False),
        sa.Column("estado_hasta", sa.String(length=20), nullable=False),
        sa.Column("rol_permitido", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "estado_desde",
            "estado_hasta",
            "rol_permitido",
            name="uq_task_transition",
        ),
    )

    feature_table = sa.table(
        "feature_state_transitions",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("tipo_proyecto", sa.String()),
        sa.column("estado_desde", sa.String()),
        sa.column("estado_hasta", sa.String()),
        sa.column("rol_permitido", sa.String()),
        sa.column("created_at", sa.DateTime()),
    )
    op.bulk_insert(
        feature_table,
        _seed_rows(
            _FEATURE_TRANSITIONS,
            ["tipo_proyecto", "estado_desde", "estado_hasta", "rol_permitido"],
        ),
    )

    task_table = sa.table(
        "task_state_transitions",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("estado_desde", sa.String()),
        sa.column("estado_hasta", sa.String()),
        sa.column("rol_permitido", sa.String()),
        sa.column("created_at", sa.DateTime()),
    )
    op.bulk_insert(
        task_table,
        _seed_rows(
            _TASK_TRANSITIONS,
            ["estado_desde", "estado_hasta", "rol_permitido"],
        ),
    )


def downgrade() -> None:
    op.drop_table("task_state_transitions")
    op.drop_table("feature_state_transitions")
    op.drop_index("idx_comments_user", table_name="comments")
    op.drop_index("idx_comments_entidad", table_name="comments")
    op.drop_table("comments")
