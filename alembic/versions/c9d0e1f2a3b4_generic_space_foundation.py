"""generic space foundation: blocks, views, field definitions

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB
        return JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    json_t = _json_type()

    op.create_table(
        "block_catalog",
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("manifest", json_t, nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("slug"),
    )

    op.create_table(
        "project_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("block_slug", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("config", json_t, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["block_slug"], ["block_catalog.slug"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "key", name="uq_project_block_key"),
    )
    op.create_index("idx_project_blocks_project", "project_blocks", ["project_id"])

    op.create_table(
        "project_views",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("route", sa.String(length=80), nullable=False),
        sa.Column("icon", sa.String(length=40), nullable=False, server_default="circle"),
        sa.Column("section", sa.String(length=20), nullable=False, server_default="plan"),
        sa.Column("layout", json_t, nullable=False),
        sa.Column(
            "required_capabilities",
            json_t,
            nullable=False,
        ),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "key", name="uq_project_view_key"),
    )
    op.create_index("idx_project_views_project", "project_views", ["project_id"])

    op.create_table(
        "project_field_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type_key", sa.String(length=40), nullable=False),
        sa.Column("field_key", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("field_type", sa.String(length=20), nullable=False),
        sa.Column("config", json_t, nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "entity_type_key",
            "field_key",
            name="uq_project_field_def",
        ),
    )
    op.create_index(
        "idx_project_field_defs_project_type",
        "project_field_definitions",
        ["project_id", "entity_type_key"],
    )

    op.add_column(
        "project_record_types",
        sa.Column("icon", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "project_record_types",
        sa.Column("traits", json_t, nullable=False, server_default="{}"),
    )
    op.add_column(
        "project_record_types",
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE project_records "
            "ALTER COLUMN data TYPE JSONB USING "
            "CASE WHEN data IS NULL OR data = '' THEN '{}'::jsonb "
            "ELSE data::jsonb END"
        )
    else:
        pass


def downgrade() -> None:
    op.drop_column("project_record_types", "is_system")
    op.drop_column("project_record_types", "traits")
    op.drop_column("project_record_types", "icon")
    op.drop_table("project_field_definitions")
    op.drop_table("project_views")
    op.drop_table("project_blocks")
    op.drop_table("block_catalog")
