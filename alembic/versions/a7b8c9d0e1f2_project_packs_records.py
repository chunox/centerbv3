"""project packs and generic records

Revision ID: a7b8c9d0e1f2
Revises: z6a7b8c9d0e1
Create Date: 2026-06-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "z6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_packs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("manifest", sa.Text(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_project_pack_slug"),
    )

    op.add_column(
        "projects",
        sa.Column(
            "pack_slug",
            sa.String(length=40),
            nullable=False,
            server_default="software",
        ),
    )

    op.alter_column(
        "project_workflow_definitions",
        "entity_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=40),
        existing_nullable=False,
    )

    op.create_table(
        "project_record_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("storage", sa.String(length=10), nullable=False, server_default="generic"),
        sa.Column("field_schema", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("parent_types", sa.Text(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "key", name="uq_project_record_type_key"),
    )

    op.create_table(
        "project_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("record_type", sa.String(length=40), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=40), nullable=False),
        sa.Column("data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("fecha_inicio", sa.Date(), nullable=True),
        sa.Column("fecha_fin", sa.Date(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["project_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_project_records_project_type", "project_records", ["project_id", "record_type"])
    op.create_index("idx_project_records_parent", "project_records", ["parent_id"])

    op.create_table(
        "project_record_assignees",
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["record_id"], ["project_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("record_id", "user_id"),
    )

    op.create_table(
        "project_record_dependencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("predecessor_id", sa.Uuid(), nullable=False),
        sa.Column("successor_id", sa.Uuid(), nullable=False),
        sa.Column("dependency_type", sa.String(length=20), nullable=False, server_default="finish_to_start"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["predecessor_id"], ["project_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["successor_id"], ["project_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "predecessor_id", "successor_id", name="uq_record_dependency_pair"
        ),
    )


def downgrade() -> None:
    op.drop_table("project_record_dependencies")
    op.drop_table("project_record_assignees")
    op.drop_index("idx_project_records_parent", table_name="project_records")
    op.drop_index("idx_project_records_project_type", table_name="project_records")
    op.drop_table("project_records")
    op.drop_table("project_record_types")
    op.alter_column(
        "project_workflow_definitions",
        "entity_type",
        existing_type=sa.String(length=40),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.drop_column("projects", "pack_slug")
    op.drop_table("project_packs")
