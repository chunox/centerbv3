"""Migración pack_slug: software → software-waterfall / software-scrum."""
from __future__ import annotations

from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE projects
        SET pack_slug = 'software-scrum'
        WHERE pack_slug = 'software'
          AND template_slug IN ('t6_scrum_interno', 't7_scrum_cliente')
        """
    )
    op.execute(
        """
        UPDATE projects
        SET pack_slug = 'software-waterfall'
        WHERE pack_slug = 'software'
          AND (template_slug IS NULL
               OR template_slug NOT IN ('t6_scrum_interno', 't7_scrum_cliente'))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE projects
        SET pack_slug = 'software'
        WHERE pack_slug IN ('software-waterfall', 'software-scrum')
        """
    )
