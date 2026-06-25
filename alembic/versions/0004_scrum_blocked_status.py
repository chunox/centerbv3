"""Sync status=blocked for legacy blocker data (F11).

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _fix_backlog_stories_under_sprint(session: Session) -> None:
    """Idempotente con 0003 — historias backlog con parent sprint vuelven a épica."""
    from app.models.entities import ProjectRecord

    stories = (
        session.query(ProjectRecord)
        .filter(
            ProjectRecord.record_type == "task",
            ProjectRecord.status == "backlog",
        )
        .all()
    )
    for story in stories:
        extra = dict(story.extra or {})
        if extra.get("scrum_role") != "story" or not story.parent_id:
            continue
        parent = (
            session.query(ProjectRecord)
            .filter(ProjectRecord.id == story.parent_id)
            .one_or_none()
        )
        if parent is None or parent.record_type != "sprint":
            continue
        orig = extra.get("original_parent_id")
        if not orig:
            continue
        story.parent_id = str(orig)
        extra.pop("original_parent_id", None)
        story.extra = extra


def upgrade() -> None:
    from app.domain.scrum.states import SCRUM_TERMINAL_STATES
    from app.models.entities import ProjectRecord, ProjectRecordBlocker
    from app.services.blockers.sync import (
        apply_block_to_record,
        cascade_block_to_descendants,
    )

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        blocked_roots: list[ProjectRecord] = []

        rows = (
            session.query(ProjectRecord)
            .join(
                ProjectRecordBlocker,
                ProjectRecordBlocker.record_id == ProjectRecord.id,
            )
            .filter(ProjectRecordBlocker.resolved_at.is_(None))
            .distinct()
            .all()
        )

        for record in rows:
            if record.status in SCRUM_TERMINAL_STATES:
                continue
            if record.status != "blocked":
                apply_block_to_record(record, inherited=False)
            blocked_roots.append(record)

        session.flush()

        for root in blocked_roots:
            if root.status != "blocked":
                continue
            cascade_block_to_descendants(
                session, str(root.project_id), str(root.id)
            )

        _fix_backlog_stories_under_sprint(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    from sqlalchemy import text

    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        conn.execute(text("""
            UPDATE project_records
            SET status = COALESCE(extra->>'status_before_block', 'backlog'),
                extra = extra - 'status_before_block' - 'blocked_by_inheritance'
            WHERE status = 'blocked'
              AND extra ? 'status_before_block'
              AND NOT EXISTS (
                SELECT 1 FROM project_record_blockers b
                WHERE b.record_id = project_records.id
                  AND b.resolved_at IS NULL
              )
        """))
