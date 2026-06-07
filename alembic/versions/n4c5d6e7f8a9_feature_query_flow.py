"""feature query flow states + legacy data migration

Revision ID: n4c5d6e7f8a9
Revises: m3b4c5d6e7f8
Create Date: 2026-06-05

"""

from typing import Sequence, Union

from alembic import op

revision: str = "n4c5d6e7f8a9"
down_revision: Union[str, None] = "m3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE feature_queries SET estado = 'respuesta_cliente' "
        "WHERE estado = 'pm_responde'"
    )
    op.execute(
        "UPDATE feature_queries SET estado = 'cerrada' "
        "WHERE estado = 'respondida'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE feature_queries SET estado = 'pm_responde' "
        "WHERE estado = 'respuesta_cliente'"
    )
