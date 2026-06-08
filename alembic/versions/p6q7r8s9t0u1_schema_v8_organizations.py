"""schema v8 — organizations, members, invites; projects.organization_id

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-06-07

"""

from datetime import datetime
from typing import Sequence, Union
import re
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "o5p6q7r8s9t0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_ORG_ID = uuid.UUID("33333333-3333-4333-8333-333333333301")


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or "org"


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        sa.CheckConstraint(
            "estado IN ('activa', 'suspendida')", name="chk_organizations_estado"
        ),
    )
    op.create_table(
        "organization_members",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("rol", sa.String(length=20), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "user_id", name="uq_organization_member"
        ),
        sa.CheckConstraint(
            "rol IN ('owner', 'admin', 'member')", name="chk_organization_member_rol"
        ),
    )
    op.create_index(
        "idx_organization_members_org",
        "organization_members",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "idx_organization_members_user",
        "organization_members",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "organization_invites",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("rol", sa.String(length=20), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_organization_invites_token"),
        sa.CheckConstraint(
            "rol IN ('admin', 'member')", name="chk_organization_invite_rol"
        ),
    )
    op.create_index(
        "idx_organization_invites_org",
        "organization_invites",
        ["organization_id"],
        unique=False,
    )

    op.add_column(
        "projects",
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=True),
    )

    now = datetime.utcnow()
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO organizations (id, nombre, slug, estado, created_at, updated_at)
            VALUES (:id, 'Center Demo', 'center-demo', 'activa', :now, :now)
            """
        ),
        {"id": str(DEFAULT_ORG_ID), "now": now},
    )
    bind.execute(
        sa.text(
            "UPDATE projects SET organization_id = :org_id WHERE organization_id IS NULL"
        ),
        {"org_id": str(DEFAULT_ORG_ID)},
    )
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("projects") as batch:
            batch.alter_column("organization_id", nullable=False)
            batch.create_foreign_key(
                "fk_projects_organization_id",
                "organizations",
                ["organization_id"],
                ["id"],
            )
    else:
        op.alter_column("projects", "organization_id", nullable=False)
        op.create_foreign_key(
            "fk_projects_organization_id",
            "projects",
            "organizations",
            ["organization_id"],
            ["id"],
        )

    op.create_index("idx_projects_organization", "projects", ["organization_id"])

    users = bind.execute(sa.text("SELECT DISTINCT created_by FROM projects")).fetchall()
    for (user_id,) in users:
        if user_id is None:
            continue
        existing = bind.execute(
            sa.text(
                "SELECT 1 FROM organization_members "
                "WHERE organization_id = :org AND user_id = :uid"
            ),
            {"org": str(DEFAULT_ORG_ID), "uid": str(user_id)},
        ).fetchone()
        if existing:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO organization_members
                    (id, organization_id, user_id, rol, joined_at)
                VALUES (:id, :org, :uid, 'owner', :now)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "org": str(DEFAULT_ORG_ID),
                "uid": str(user_id),
                "now": now,
            },
        )

    pm_members = bind.execute(
        sa.text(
            """
            SELECT DISTINCT pm.user_id
              FROM project_members pm
              JOIN projects p ON p.id = pm.project_id
             WHERE pm.rol = 'pm'
               AND p.organization_id = :org
               AND pm.user_id NOT IN (
                   SELECT user_id FROM organization_members
                    WHERE organization_id = :org
               )
            """
        ),
        {"org": str(DEFAULT_ORG_ID)},
    ).fetchall()
    for (user_id,) in pm_members:
        bind.execute(
            sa.text(
                """
                INSERT INTO organization_members
                    (id, organization_id, user_id, rol, joined_at)
                VALUES (:id, :org, :uid, 'admin', :now)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "org": str(DEFAULT_ORG_ID),
                "uid": str(user_id),
                "now": now,
            },
        )


def downgrade() -> None:
    op.drop_index("idx_projects_organization", table_name="projects")
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("projects") as batch:
            batch.drop_constraint("fk_projects_organization_id", type_="foreignkey")
            batch.drop_column("organization_id")
    else:
        op.drop_constraint("fk_projects_organization_id", "projects", type_="foreignkey")
        op.drop_column("projects", "organization_id")

    op.drop_index("idx_organization_invites_org", table_name="organization_invites")
    op.drop_table("organization_invites")
    op.drop_index("idx_organization_members_user", table_name="organization_members")
    op.drop_index("idx_organization_members_org", table_name="organization_members")
    op.drop_table("organization_members")
    op.drop_table("organizations")
