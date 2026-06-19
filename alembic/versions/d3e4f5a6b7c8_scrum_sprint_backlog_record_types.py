"""Scrum: migrar sprint/backlog de milestone a record types propios

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCRUM_TEMPLATES = ("t6_scrum_interno", "t7_scrum_cliente")


def _migrate_records(bind, *, to_type: str, tipo_value: str, estado: str | None = None) -> None:
    dialect = bind.dialect.name
    tipo_filter = (
        "json_extract(data, '$.tipo') = :tipo"
        if dialect == "sqlite"
        else "data->>'tipo' = :tipo"
    )
    estado_sql = f", estado = '{estado}'" if estado else ""
    for tpl in SCRUM_TEMPLATES:
        bind.execute(
            sa.text(
                f"""
                UPDATE project_records
                SET record_type = :to_type{estado_sql}
                WHERE record_type = 'milestone'
                  AND {tipo_filter}
                  AND project_id IN (
                      SELECT id FROM projects WHERE template_slug = :tpl
                  )
                """
            ),
            {"to_type": to_type, "tipo": tipo_value, "tpl": tpl},
        )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    _migrate_records(bind, to_type="product_backlog", tipo_value="product_backlog", estado="activo")
    _migrate_records(bind, to_type="sprint", tipo_value="sprint")

    if dialect == "sqlite":
        for tpl in SCRUM_TEMPLATES:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO project_record_types (
                        id, project_id, key, label, parent_types, field_schema,
                        icon, traits, is_system, orden, created_at
                    )
                    SELECT
                        lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' ||
                              substr(hex(randomblob(2)), 2) || '-' ||
                              substr('89ab', abs(random()) % 4 + 1, 1) ||
                              substr(hex(randomblob(2)), 2) || '-' ||
                              hex(randomblob(6))),
                        p.id,
                        et.key,
                        et.label,
                        et.parent_types,
                        '[]',
                        et.icon,
                        '{}',
                        1,
                        et.orden,
                        datetime('now')
                    FROM projects p
                    CROSS JOIN (
                        SELECT 'product_backlog' AS key, 'Product Backlog' AS label,
                               NULL AS parent_types, NULL AS icon, 7 AS orden
                        UNION ALL
                        SELECT 'sprint', 'Sprint', NULL, 'timer', 8
                    ) AS et
                    WHERE p.template_slug = :tpl
                      AND p.pack_slug = 'software'
                      AND NOT EXISTS (
                          SELECT 1 FROM project_record_types rt
                          WHERE rt.project_id = p.id AND rt.key = et.key
                      )
                    """
                ),
                {"tpl": tpl},
            )
        bind.execute(
            sa.text(
                """
                UPDATE project_record_types
                SET parent_types = '["product_backlog", "sprint"]'
                WHERE key = 'task'
                  AND project_id IN (
                      SELECT id FROM projects
                      WHERE template_slug IN ('t6_scrum_interno', 't7_scrum_cliente')
                  )
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE project_record_types
                SET parent_types = '["sprint"]'
                WHERE key = 'impediment'
                  AND project_id IN (
                      SELECT id FROM projects
                      WHERE template_slug IN ('t6_scrum_interno', 't7_scrum_cliente')
                  )
                """
            )
        )
    else:
        bind.execute(
            sa.text(
                """
                INSERT INTO project_record_types (
                    id, project_id, key, label, parent_types, field_schema,
                    icon, traits, is_system, orden, created_at
                )
                SELECT
                    gen_random_uuid(),
                    p.id,
                    et.key,
                    et.label,
                    et.parent_types,
                    '[]'::json,
                    et.icon,
                    '{}'::json,
                    true,
                    et.orden,
                    NOW()
                FROM projects p
                CROSS JOIN (
                    VALUES
                        ('product_backlog', 'Product Backlog', NULL::json, NULL::text, 7),
                        ('sprint', 'Sprint', NULL::json, 'timer', 8)
                ) AS et(key, label, parent_types, icon, orden)
                WHERE p.template_slug IN ('t6_scrum_interno', 't7_scrum_cliente')
                  AND p.pack_slug = 'software'
                  AND NOT EXISTS (
                      SELECT 1 FROM project_record_types rt
                      WHERE rt.project_id = p.id AND rt.key = et.key
                  )
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE project_record_types
                SET parent_types = '["product_backlog", "sprint"]'::json
                WHERE key = 'task'
                  AND project_id IN (
                      SELECT id FROM projects
                      WHERE template_slug IN ('t6_scrum_interno', 't7_scrum_cliente')
                  )
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE project_record_types
                SET parent_types = '["sprint"]'::json
                WHERE key = 'impediment'
                  AND project_id IN (
                      SELECT id FROM projects
                      WHERE template_slug IN ('t6_scrum_interno', 't7_scrum_cliente')
                  )
                """
            )
        )

    bind.execute(
        sa.text(
            """
            DELETE FROM project_record_types
            WHERE key = 'milestone'
              AND project_id IN (
                  SELECT id FROM projects
                  WHERE template_slug IN ('t6_scrum_interno', 't7_scrum_cliente')
              )
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    for tpl in SCRUM_TEMPLATES:
        if dialect == "sqlite":
            bind.execute(
                sa.text(
                    """
                    UPDATE project_records
                    SET record_type = 'milestone',
                        data = json_set(COALESCE(data, '{}'), '$.tipo', 'product_backlog')
                    WHERE record_type = 'product_backlog'
                      AND project_id IN (
                          SELECT id FROM projects WHERE template_slug = :tpl
                      )
                    """
                ),
                {"tpl": tpl},
            )
            bind.execute(
                sa.text(
                    """
                    UPDATE project_records
                    SET record_type = 'milestone',
                        data = json_set(COALESCE(data, '{}'), '$.tipo', 'sprint')
                    WHERE record_type = 'sprint'
                      AND project_id IN (
                          SELECT id FROM projects WHERE template_slug = :tpl
                      )
                    """
                ),
                {"tpl": tpl},
            )
        else:
            bind.execute(
                sa.text(
                    """
                    UPDATE project_records pr
                    SET record_type = 'milestone',
                        data = COALESCE(pr.data, '{}'::jsonb) || '{"tipo": "product_backlog"}'::jsonb
                    FROM projects p
                    WHERE pr.project_id = p.id
                      AND p.template_slug = :tpl
                      AND pr.record_type = 'product_backlog'
                    """
                ),
                {"tpl": tpl},
            )
            bind.execute(
                sa.text(
                    """
                    UPDATE project_records pr
                    SET record_type = 'milestone',
                        data = COALESCE(pr.data, '{}'::jsonb) || '{"tipo": "sprint"}'::jsonb
                    FROM projects p
                    WHERE pr.project_id = p.id
                      AND p.template_slug = :tpl
                      AND pr.record_type = 'sprint'
                    """
                ),
                {"tpl": tpl},
            )
