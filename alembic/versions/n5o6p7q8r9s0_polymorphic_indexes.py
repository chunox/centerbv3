"""Add composite indexes on polymorphic (entidad_tipo, entidad_id) columns

Covers: comments, audit_logs, notifications, attachment_relations.
No FK constraint is possible with a polymorphic pattern; indexes cover the
common lookup pattern (filter by tipo + id).

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-06-14
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "n5o6p7q8r9s0"
down_revision: Union[str, None] = "m4n5o6p7q8r9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    # (index_name, table, columns)
    ("ix_comments_entidad", "comments", ["entidad_tipo", "entidad_id"]),
    ("ix_comments_entidad_id", "comments", ["entidad_id"]),
    ("ix_audit_logs_entidad", "audit_logs", ["entidad_tipo", "entidad_id"]),
    ("ix_audit_logs_project", "audit_logs", ["project_id", "entidad_tipo"]),
    ("ix_notifications_entidad", "notifications", ["entidad_tipo", "entidad_id"]),
    ("ix_notifications_user_leida", "notifications", ["user_id", "leida"]),
    ("ix_attachment_relations_entidad", "attachment_relations", ["entidad_tipo", "entidad_id"]),
]


def upgrade() -> None:
    for name, table, cols in _INDEXES:
        op.create_index(name, table, cols)


def downgrade() -> None:
    for name, table, _cols in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
