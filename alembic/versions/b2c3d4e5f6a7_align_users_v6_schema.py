"""align users table with center_schema_v6

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("name", new_column_name="nombre")
        batch_op.add_column(
            sa.Column("password_hash", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("avatar_url", sa.String(length=500), nullable=True)
        )
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    op.execute(
        "UPDATE users SET password_hash = 'migracion_sin_password', "
        "updated_at = created_at WHERE password_hash IS NULL"
    )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "password_hash", existing_type=sa.String(length=255), nullable=False
        )
        batch_op.alter_column(
            "updated_at", existing_type=sa.DateTime(), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("avatar_url")
        batch_op.drop_column("password_hash")
        batch_op.alter_column("nombre", new_column_name="name")
