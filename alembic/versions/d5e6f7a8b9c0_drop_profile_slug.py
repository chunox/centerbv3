"""drop profile_slug from projects

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-15

profile_slug is now a computed Python property on Project derived from
template_slug. The column is no longer persisted to the database.
"""

from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("profile_slug")


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(
            sa.Column(
                "profile_slug",
                sa.String(length=40),
                nullable=False,
                server_default="default",
            )
        )
