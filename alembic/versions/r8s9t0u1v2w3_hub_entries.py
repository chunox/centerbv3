"""hub_entries + document_exposures.hub_entry_id

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-06-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "r8s9t0u1v2w3"
down_revision: Union[str, None] = "q7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_EXPOSURE_TARGET = (
    "(document_id IS NOT NULL AND attachment_id IS NULL AND hub_entry_id IS NULL) "
    "OR (document_id IS NULL AND attachment_id IS NOT NULL AND hub_entry_id IS NULL) "
    "OR (document_id IS NULL AND attachment_id IS NULL AND hub_entry_id IS NOT NULL)"
)

_OLD_EXPOSURE_TARGET = (
    "(document_id IS NOT NULL AND attachment_id IS NULL) "
    "OR (document_id IS NULL AND attachment_id IS NOT NULL)"
)


def _has_table(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    cols = inspect(op.get_bind()).get_columns(table)
    return any(c["name"] == column for c in cols)


def _has_index(table: str, index: str) -> bool:
    indexes = inspect(op.get_bind()).get_indexes(table)
    return any(i["name"] == index for i in indexes)


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _cleanup_sqlite_batch_artifacts() -> None:
    """Restos de un batch_alter_table interrumpido."""
    if not _is_sqlite():
        return
    op.execute(text("DROP TABLE IF EXISTS _alembic_tmp_document_exposures"))


def upgrade() -> None:
    _cleanup_sqlite_batch_artifacts()

    if not _has_table("hub_entries"):
        op.create_table(
            "hub_entries",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column("author_id", sa.Uuid(), nullable=False),
            sa.Column("tipo", sa.String(length=10), nullable=False),
            sa.Column("titulo", sa.String(length=255), nullable=True),
            sa.Column("contenido", sa.Text(), nullable=False),
            sa.Column("visibilidad", sa.String(length=10), nullable=False, server_default="publico"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("tipo IN ('update', 'note')", name="chk_hub_entry_tipo"),
            sa.CheckConstraint(
                "visibilidad IN ('publico', 'interno')", name="chk_hub_entry_visibilidad"
            ),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if _has_table("hub_entries") and not _has_index("hub_entries", "idx_hub_entries_project"):
        op.create_index("idx_hub_entries_project", "hub_entries", ["project_id"])

    if _has_table("document_exposures") and not _has_column("document_exposures", "hub_entry_id"):
        if _is_sqlite():
            op.execute(
                text(
                    "ALTER TABLE document_exposures "
                    "ADD COLUMN hub_entry_id CHAR(32) "
                    "REFERENCES hub_entries(id) ON DELETE CASCADE"
                )
            )
        else:
            with op.batch_alter_table("document_exposures") as batch_op:
                batch_op.add_column(sa.Column("hub_entry_id", sa.Uuid(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_document_exposures_hub_entry",
                    "hub_entries",
                    ["hub_entry_id"],
                    ["id"],
                    ondelete="CASCADE",
                )

    if _has_table("document_exposures") and _has_column("document_exposures", "hub_entry_id"):
        _cleanup_sqlite_batch_artifacts()
        with op.batch_alter_table("document_exposures") as batch_op:
            try:
                batch_op.drop_constraint("chk_exposure_target", type_="check")
            except Exception:
                pass
            batch_op.create_check_constraint("chk_exposure_target", _NEW_EXPOSURE_TARGET)


def downgrade() -> None:
    if _has_table("document_exposures"):
        _cleanup_sqlite_batch_artifacts()
        with op.batch_alter_table("document_exposures") as batch_op:
            try:
                batch_op.drop_constraint("chk_exposure_target", type_="check")
            except Exception:
                pass
            batch_op.create_check_constraint("chk_exposure_target", _OLD_EXPOSURE_TARGET)

    if _has_table("document_exposures") and _has_column("document_exposures", "hub_entry_id"):
        if _is_sqlite():
            _cleanup_sqlite_batch_artifacts()
            # SQLite no soporta DROP COLUMN en versiones antiguas; batch para PG.
            with op.batch_alter_table("document_exposures") as batch_op:
                batch_op.drop_column("hub_entry_id")
        else:
            with op.batch_alter_table("document_exposures") as batch_op:
                try:
                    batch_op.drop_constraint("fk_document_exposures_hub_entry", type_="foreignkey")
                except Exception:
                    pass
                batch_op.drop_column("hub_entry_id")

    if _has_table("hub_entries"):
        if _has_index("hub_entries", "idx_hub_entries_project"):
            op.drop_index("idx_hub_entries_project", table_name="hub_entries")
        op.drop_table("hub_entries")
