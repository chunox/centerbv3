"""Unify status vocabulary — migrate old Spanish/mixed status strings to unified English set.

Work item states (epics, stories, dev_tasks, subtasks, waterfall features/milestones/tasks):
  product_backlog → backlog  (scrum epics/stories not in sprint)
  pendiente       → to_do    (scrum stories committed to sprint)
  pendiente       → backlog  (waterfall milestone/feature/task — initial state)
  en_progreso     → in_progress
  en_revision     → in_review
  completado      → done
  cancelado       → cancelled
  completed       → done     (dev_task, subtask, waterfall task)
  cancel          → cancelled (dev_task, subtask, waterfall task)

Sprint operational states (pendiente, activo, cerrado, cancelado) are intentionally preserved.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Scrum: epics and stories in backlog (not committed to any sprint) ──
    # product_backlog → backlog  (scrum epics with scrum_role=epic or story)
    conn.execute(text("""
        UPDATE project_records
        SET status = 'backlog'
        WHERE status = 'product_backlog'
          AND record_type != 'sprint'
    """))

    # ── Scrum: stories committed to sprint (pendiente → to_do) ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'to_do'
        WHERE status = 'pendiente'
          AND extra->>'scrum_role' = 'story'
    """))

    # ── Waterfall: milestone/feature/task initial state (pendiente → backlog) ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'backlog'
        WHERE status = 'pendiente'
          AND record_type IN ('milestone', 'feature', 'task')
          AND (extra->>'scrum_role' IS NULL OR extra->>'scrum_role' NOT IN ('story', 'epic', 'dev', 'subtask'))
    """))

    # ── en_progreso → in_progress (all work items) ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'in_progress'
        WHERE status = 'en_progreso'
          AND record_type != 'sprint'
    """))

    # ── en_revision → in_review (all work items) ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'in_review'
        WHERE status = 'en_revision'
          AND record_type != 'sprint'
    """))

    # ── completado → done (scrum + waterfall) ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'done'
        WHERE status = 'completado'
          AND record_type != 'sprint'
    """))

    # ── cancelado → cancelled (scrum + waterfall) ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'cancelled'
        WHERE status = 'cancelado'
          AND record_type != 'sprint'
    """))

    # ── completed → done (dev_task, subtask, waterfall task) ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'done'
        WHERE status = 'completed'
    """))

    # ── cancel → cancelled (dev_task, subtask, waterfall task) ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'cancelled'
        WHERE status = 'cancel'
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # ── Reverse: backlog → product_backlog for scrum epics/stories ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'product_backlog'
        WHERE status = 'backlog'
          AND extra->>'scrum_role' IN ('epic', 'story')
    """))

    # ── Reverse: backlog → pendiente for waterfall + scrum items without scrum_role ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'pendiente'
        WHERE status = 'backlog'
          AND record_type IN ('milestone', 'feature', 'task')
          AND (extra->>'scrum_role' IS NULL OR extra->>'scrum_role' NOT IN ('epic', 'story', 'dev', 'subtask'))
    """))

    # ── Reverse: to_do → pendiente for scrum stories ──
    conn.execute(text("""
        UPDATE project_records
        SET status = 'pendiente'
        WHERE status = 'to_do'
          AND extra->>'scrum_role' = 'story'
    """))

    conn.execute(text("UPDATE project_records SET status = 'en_progreso' WHERE status = 'in_progress' AND record_type != 'sprint'"))
    conn.execute(text("UPDATE project_records SET status = 'en_revision' WHERE status = 'in_review'"))
    conn.execute(text("UPDATE project_records SET status = 'completado' WHERE status = 'done' AND record_type IN ('milestone', 'feature', 'task') AND (extra->>'scrum_role' IS NULL OR extra->>'scrum_role' IN ('epic', 'story'))"))
    conn.execute(text("UPDATE project_records SET status = 'completed' WHERE status = 'done' AND extra->>'scrum_role' IN ('dev', 'subtask')"))
    conn.execute(text("UPDATE project_records SET status = 'cancelado' WHERE status = 'cancelled' AND record_type IN ('milestone', 'feature') AND (extra->>'scrum_role' IS NULL OR extra->>'scrum_role' IN ('epic', 'story'))"))
    conn.execute(text("UPDATE project_records SET status = 'cancel' WHERE status = 'cancelled' AND extra->>'scrum_role' IN ('dev', 'subtask')"))
