"""schema v7 — Kanban tasks, uat, queries, document_exposures

Revision ID: o5p6q7r8s9t0
Revises: n4c5d6e7f8a9
Create Date: 2026-06-05

"""

from datetime import datetime
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, None] = "n4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TASK_TRANSITIONS_V7 = [
    ("backlog", "to_do", "dev"),
    ("to_do", "in_progress", "dev"),
    ("in_progress", "to_do", "dev"),
    ("in_progress", "ready_for_test", "dev"),
    ("ready_for_test", "in_progress", "dev"),
    ("ready_for_test", "completed", "dev"),
    ("completed", "in_progress", "dev"),
    ("backlog", "cancel", "dev"),
    ("to_do", "cancel", "dev"),
    ("in_progress", "cancel", "dev"),
    ("ready_for_test", "cancel", "dev"),
]


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _seed_rows(rows: list[tuple[str, ...]], columns: list[str]) -> list[dict]:
    now = datetime.utcnow()
    return [
        {**dict(zip(columns, row, strict=True)), "id": uuid.uuid4(), "created_at": now}
        for row in rows
    ]


def _migrate_data_v7() -> None:
    op.execute("UPDATE tasks SET estado = 'backlog' WHERE estado = 'abierto'")
    op.execute(
        "UPDATE tasks SET estado = 'in_progress' WHERE estado = 'en_desarrollo'"
    )
    op.execute("UPDATE tasks SET estado = 'completed' WHERE estado = 'cerrado'")
    op.execute("UPDATE tasks SET estado = 'cancel' WHERE estado = 'cancelado'")

    op.execute("UPDATE features SET estado = 'uat' WHERE estado = 'en_qa'")
    op.execute(
        "UPDATE features SET tipo = 'desarrollo' WHERE tipo = 'mantenimiento'"
    )

    op.execute(
        "UPDATE feature_queries SET estado = 'respuesta_cliente' "
        "WHERE estado = 'pm_responde'"
    )
    op.execute(
        "UPDATE feature_queries SET estado = 'cerrada' "
        "WHERE estado = 'respondida'"
    )

    op.execute(
        "UPDATE milestones SET tipo = 'entrega' WHERE tipo = 'mantenimiento'"
    )
    op.execute(
        """
        UPDATE milestones SET estado = 'en_progreso_con_bug'
        WHERE estado = 'cerrado_con_pendientes'
          AND EXISTS (
              SELECT 1 FROM features f
               WHERE f.milestone_id = milestones.id
                 AND f.tipo = 'bug'
                 AND f.estado NOT IN ('completado', 'cancelado')
          )
        """
    )
    op.execute(
        "UPDATE milestones SET estado = 'en_progreso' "
        "WHERE estado = 'cerrado_con_pendientes'"
    )


def _reseed_transitions() -> None:
    op.execute(
        "DELETE FROM feature_state_transitions "
        "WHERE (estado_desde = 'pendiente' AND estado_hasta = 'en_progreso') "
        "   OR (estado_desde = 'en_progreso' AND estado_hasta = 'en_qa')"
    )
    op.execute(
        "UPDATE feature_state_transitions SET estado_desde = 'uat' "
        "WHERE estado_desde = 'en_qa'"
    )
    op.execute(
        "UPDATE feature_state_transitions SET estado_hasta = 'uat' "
        "WHERE estado_hasta = 'en_qa'"
    )

    conn = op.get_bind()
    missing = conn.execute(
        sa.text(
            "SELECT 1 FROM feature_state_transitions "
            "WHERE tipo_proyecto = 'ambos' "
            "  AND estado_desde = 'en_progreso' "
            "  AND estado_hasta = 'uat' "
            "  AND rol_permitido = 'dev'"
        )
    ).fetchone()
    if not missing:
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
                [("ambos", "en_progreso", "uat", "dev")],
                ["tipo_proyecto", "estado_desde", "estado_hasta", "rol_permitido"],
            ),
        )

    op.execute("DELETE FROM task_state_transitions")
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
            _TASK_TRANSITIONS_V7,
            ["estado_desde", "estado_hasta", "rol_permitido"],
        ),
    )


def _migrate_document_exposures() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, project_id, created_by FROM documents "
            "WHERE visibilidad = 'cliente'"
        )
    ).fetchall()
    if not rows:
        op.execute(
            "UPDATE documents SET visibilidad = 'interno' "
            "WHERE visibilidad = 'cliente'"
        )
        return

    now = datetime.utcnow()
    exposure_table = sa.table(
        "document_exposures",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("project_id", sa.Uuid(as_uuid=True)),
        sa.column("ambito", sa.String()),
        sa.column("document_id", sa.Uuid(as_uuid=True)),
        sa.column("expuesto_por", sa.Uuid(as_uuid=True)),
        sa.column("created_at", sa.DateTime()),
    )
    op.bulk_insert(
        exposure_table,
        [
            {
                "id": uuid.uuid4(),
                "project_id": row.project_id,
                "ambito": "proyecto",
                "document_id": row.id,
                "expuesto_por": row.created_by,
                "created_at": now,
            }
            for row in rows
        ],
    )
    op.execute(
        "UPDATE documents SET visibilidad = 'interno' WHERE visibilidad = 'cliente'"
    )


def upgrade() -> None:
    _migrate_data_v7()

    op.execute("DROP INDEX IF EXISTS uq_milestone_mantenimiento")

    with op.batch_alter_table("features", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("origen_feature_id", sa.Uuid(as_uuid=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_features_origen_feature",
            "features",
            ["origen_feature_id"],
            ["id"],
        )
        batch_op.create_index(
            "idx_features_origen_feature", ["origen_feature_id"], unique=False
        )

    op.create_table(
        "document_exposures",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("ambito", sa.String(length=20), nullable=False),
        sa.Column("milestone_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("feature_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("attachment_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("titulo_visible", sa.String(length=255), nullable=True),
        sa.Column("expuesto_por", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(document_id IS NOT NULL AND attachment_id IS NULL) "
            "OR (document_id IS NULL AND attachment_id IS NOT NULL)",
            name="chk_exposure_target",
        ),
        sa.CheckConstraint(
            "(ambito = 'proyecto' AND milestone_id IS NULL AND feature_id IS NULL) "
            "OR (ambito = 'milestone' AND milestone_id IS NOT NULL "
            "AND feature_id IS NULL) "
            "OR (ambito = 'feature' AND feature_id IS NOT NULL)",
            name="chk_exposure_ambito",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["milestones.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["features.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["expuesto_por"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_document_exposures_project", "document_exposures", ["project_id"]
    )
    op.create_index(
        "idx_document_exposures_milestone",
        "document_exposures",
        ["milestone_id"],
    )
    op.create_index(
        "idx_document_exposures_feature", "document_exposures", ["feature_id"]
    )

    _migrate_document_exposures()
    _reseed_transitions()

    if _is_postgresql():
        op.execute(
            """
            UPDATE features f SET bloqueada = EXISTS (
                SELECT 1 FROM feature_queries q
                 WHERE q.feature_id = f.id
                   AND q.estado IN (
                       'pendiente_aprobacion_pm',
                       'esperando_cliente',
                       'respuesta_cliente',
                       'esperando_pm'
                   )
            )
            """
        )


def downgrade() -> None:
    op.drop_index("idx_document_exposures_feature", table_name="document_exposures")
    op.drop_index(
        "idx_document_exposures_milestone", table_name="document_exposures"
    )
    op.drop_index("idx_document_exposures_project", table_name="document_exposures")
    op.drop_table("document_exposures")

    with op.batch_alter_table("features", schema=None) as batch_op:
        batch_op.drop_index("idx_features_origen_feature")
        batch_op.drop_constraint("fk_features_origen_feature", type_="foreignkey")
        batch_op.drop_column("origen_feature_id")

    op.execute("UPDATE tasks SET estado = 'abierto' WHERE estado = 'backlog'")
    op.execute(
        "UPDATE tasks SET estado = 'en_desarrollo' WHERE estado = 'in_progress'"
    )
    op.execute("UPDATE tasks SET estado = 'cerrado' WHERE estado = 'completed'")
    op.execute("UPDATE tasks SET estado = 'cancelado' WHERE estado = 'cancel'")

    op.execute("UPDATE features SET estado = 'en_qa' WHERE estado = 'uat'")

    op.execute(
        "UPDATE feature_queries SET estado = 'pm_responde' "
        "WHERE estado = 'respuesta_cliente'"
    )

    op.execute(
        "DELETE FROM feature_state_transitions "
        "WHERE estado_desde = 'en_progreso' AND estado_hasta = 'uat'"
    )
    op.execute(
        "UPDATE feature_state_transitions SET estado_desde = 'en_qa' "
        "WHERE estado_desde = 'uat'"
    )
    op.execute(
        "UPDATE feature_state_transitions SET estado_hasta = 'en_qa' "
        "WHERE estado_hasta = 'uat'"
    )

    op.execute("DELETE FROM task_state_transitions")
