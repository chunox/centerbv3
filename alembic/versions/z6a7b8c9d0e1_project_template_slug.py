"""project template_slug column

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
Create Date: 2026-06-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z6a7b8c9d0e1"
down_revision: Union[str, None] = "y5z6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "template_slug",
            sa.String(length=40),
            nullable=False,
            server_default="t1_cliente_clasico",
        ),
    )
    op.execute(
        """
        UPDATE projects
        SET template_slug = CASE
            WHEN tipo = 'interno' THEN 't3_interno_clasico'
            ELSE 't1_cliente_clasico'
        END
        """
    )


def downgrade() -> None:
    op.drop_column("projects", "template_slug")
