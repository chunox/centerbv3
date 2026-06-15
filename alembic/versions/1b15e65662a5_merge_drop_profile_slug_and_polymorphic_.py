"""merge_drop_profile_slug_and_polymorphic_indexes

Revision ID: 1b15e65662a5
Revises: d5e6f7a8b9c0, n5o6p7q8r9s0
Create Date: 2026-06-15 13:03:16.255440

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b15e65662a5'
down_revision: Union[str, None] = ('d5e6f7a8b9c0', 'n5o6p7q8r9s0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
