"""Merge: record_blockers + split_software_packs → único head

Revision ID: f5a6b8c9d1e2
Revises: e4f5a6b8c9d1, f5a6b7c8d9e0
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "f5a6b8c9d1e2"
down_revision: Union[str, tuple, None] = ("e4f5a6b8c9d1", "f5a6b7c8d9e0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
