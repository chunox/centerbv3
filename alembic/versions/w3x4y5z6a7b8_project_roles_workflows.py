"""project roles, capabilities, workflows, workbenches

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-06-09

"""

from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w3x4y5z6a7b8"
down_revision: Union[str, None] = "v2w3x4y5z6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _seed_roles_for_project(conn, project_id: str, tipo: str) -> dict[str, str]:
    from app.domain.capabilities import LEGACY_ROLE_CAPABILITIES
    from app.domain.workflow_templates import workflow_for_project_tipo
    from app.domain.workbenches import DEFAULT_WORKBENCHES

    existing = conn.execute(
        sa.text("SELECT slug, id FROM project_roles WHERE project_id = :pid"),
        {"pid": project_id},
    ).fetchall()
    if existing:
        return {slug: str(rid) for slug, rid in existing}

    role_ids: dict[str, str] = {}
    system_roles = [
        ("pm", "PM", 1),
        ("dev", "Dev", 2),
        ("qa", "QA", 3),
        ("cliente", "Cliente", 4),
    ]
    for slug, nombre, orden in system_roles:
        role_id = str(uuid.uuid4())
        role_ids[slug] = role_id
        conn.execute(
            sa.text(
                """
                INSERT INTO project_roles (id, project_id, slug, nombre, is_system, orden, created_at)
                VALUES (:id, :project_id, :slug, :nombre, 1, :orden, datetime('now'))
                """
            ),
            {"id": role_id, "project_id": project_id, "slug": slug, "nombre": nombre, "orden": orden},
        )
        for cap in LEGACY_ROLE_CAPABILITIES.get(slug, frozenset()):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO project_role_capabilities (id, role_id, capability_key)
                    VALUES (:id, :role_id, :cap)
                    """
                ),
                {"id": str(uuid.uuid4()), "role_id": role_id, "cap": cap},
            )

    for entity_type in ("feature", "task", "query", "report"):
        has_wf = conn.execute(
            sa.text(
                """
                SELECT 1 FROM project_workflow_definitions
                WHERE project_id = :pid AND entity_type = :et LIMIT 1
                """
            ),
            {"pid": project_id, "et": entity_type},
        ).fetchone()
        if has_wf:
            continue
        wf = workflow_for_project_tipo(tipo, entity_type)
        conn.execute(
            sa.text(
                """
                INSERT INTO project_workflow_definitions
                (id, project_id, entity_type, version, is_active, definition, created_at)
                VALUES (:id, :project_id, :entity_type, 1, 1, :definition, datetime('now'))
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "entity_type": entity_type,
                "definition": json.dumps(wf, ensure_ascii=False),
            },
        )

    has_wb = conn.execute(
        sa.text(
            "SELECT 1 FROM project_workbench_definitions WHERE project_id = :pid LIMIT 1"
        ),
        {"pid": project_id},
    ).fetchone()
    if not has_wb:
        conn.execute(
            sa.text(
                """
                INSERT INTO project_workbench_definitions (id, project_id, definition, updated_at)
                VALUES (:id, :project_id, :definition, datetime('now'))
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "definition": json.dumps(DEFAULT_WORKBENCHES, ensure_ascii=False),
            },
        )
    return role_ids


def _table_names(conn) -> set[str]:
    return {r[0] for r in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}


def _column_names(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(sa.text(f"PRAGMA table_info({table})"))}


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)

    if "project_roles" not in tables:
        op.create_table(
            "project_roles",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("slug", sa.String(40), nullable=False),
            sa.Column("nombre", sa.String(80), nullable=False),
            sa.Column("descripcion", sa.Text(), nullable=True),
            sa.Column("color", sa.String(20), nullable=True),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("project_id", "slug", name="uq_project_role_slug"),
        )
        op.create_table(
            "project_role_capabilities",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("role_id", sa.Uuid(), sa.ForeignKey("project_roles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("capability_key", sa.String(80), nullable=False),
            sa.UniqueConstraint("role_id", "capability_key", name="uq_role_capability"),
        )
        op.create_table(
            "project_workflow_definitions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("entity_type", sa.String(20), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("definition", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("project_id", "entity_type", "version", name="uq_project_workflow_version"),
        )
        op.create_table(
            "project_workbench_definitions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("definition", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    member_cols = _column_names(conn, "project_members")
    if "role_id" not in member_cols:
        op.add_column("project_members", sa.Column("role_id", sa.Uuid(), nullable=True))

    projects = conn.execute(sa.text("SELECT id, tipo FROM projects")).fetchall()
    for project_id, tipo in projects:
        pid = str(project_id)
        role_ids = _seed_roles_for_project(conn, pid, tipo or "con_cliente")
        members = conn.execute(
            sa.text("SELECT id, rol, role_id FROM project_members WHERE project_id = :pid"),
            {"pid": pid},
        ).fetchall()
        for member_id, rol, existing_role_id in members:
            if existing_role_id:
                continue
            rid = role_ids.get(rol) if rol else None
            if rid:
                conn.execute(
                    sa.text("UPDATE project_members SET role_id = :rid WHERE id = :mid"),
                    {"rid": rid, "mid": str(member_id)},
                )

    member_cols = _column_names(conn, "project_members")
    if "rol" in member_cols:
        with op.batch_alter_table("project_members", recreate="always") as batch_op:
            batch_op.alter_column("role_id", nullable=False)
            batch_op.drop_column("rol")
            batch_op.create_foreign_key(
                "fk_project_members_role_id",
                "project_roles",
                ["role_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_unique_constraint(
                "uq_project_member", ["project_id", "user_id", "role_id"]
            )
    else:
        try:
            op.create_foreign_key(
                "fk_project_members_role_id",
                "project_members",
                "project_roles",
                ["role_id"],
                ["id"],
                ondelete="CASCADE",
            )
        except Exception:
            pass
        try:
            op.create_unique_constraint(
                "uq_project_member", "project_members", ["project_id", "user_id", "role_id"]
            )
        except Exception:
            pass


def downgrade() -> None:
    conn = op.get_bind()
    member_cols = _column_names(conn, "project_members")
    if "rol" not in member_cols:
        op.add_column("project_members", sa.Column("rol", sa.String(20), nullable=True))
        rows = conn.execute(
            sa.text(
                """
                SELECT pm.id, pr.slug
                FROM project_members pm
                JOIN project_roles pr ON pr.id = pm.role_id
                """
            )
        ).fetchall()
        for member_id, slug in rows:
            conn.execute(
                sa.text("UPDATE project_members SET rol = :slug WHERE id = :mid"),
                {"slug": slug, "mid": str(member_id)},
            )
        try:
            op.drop_constraint("uq_project_member", "project_members", type_="unique")
        except Exception:
            pass
        try:
            op.drop_constraint("fk_project_members_role_id", "project_members", type_="foreignkey")
        except Exception:
            pass
        op.drop_column("project_members", "role_id")
        op.alter_column("project_members", "rol", nullable=False)
        op.create_unique_constraint("uq_project_member", "project_members", ["project_id", "user_id", "rol"])
    op.drop_table("project_workbench_definitions")
    op.drop_table("project_workflow_definitions")
    op.drop_table("project_role_capabilities")
    op.drop_table("project_roles")
