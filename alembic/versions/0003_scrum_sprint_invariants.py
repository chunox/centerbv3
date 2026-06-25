"""Scrum sprint membership invariants — fix inconsistent parent/sprint_id data.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-25
"""
from alembic import op
from sqlalchemy import text

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ACTIVE_STORY_STATUSES = ("to_do", "in_progress", "in_review", "done")
ACTIVE_EPIC_STATUSES = ("to_do", "in_progress", "in_review", "done")


def upgrade() -> None:
    conn = op.get_bind()

    # Story in active status but parent is epic (not sprint) → reparent to active sprint or reset backlog
    conn.execute(text("""
        UPDATE project_records AS story
        SET parent_id = active_sprint.id,
            extra = jsonb_set(
                COALESCE(story.extra, '{}'::jsonb),
                '{original_parent_id}',
                to_jsonb(story.parent_id::text),
                true
            )
        FROM project_records AS parent,
             project_records AS active_sprint
        WHERE story.record_type = 'task'
          AND story.extra->>'scrum_role' = 'story'
          AND story.status IN ('to_do', 'in_progress', 'in_review', 'done')
          AND story.parent_id = parent.id
          AND parent.record_type = 'task'
          AND parent.extra->>'scrum_role' = 'epic'
          AND active_sprint.project_id = story.project_id
          AND active_sprint.record_type = 'sprint'
          AND active_sprint.status = 'activo'
    """))

    conn.execute(text("""
        UPDATE project_records AS story
        SET status = 'backlog'
        WHERE story.record_type = 'task'
          AND story.extra->>'scrum_role' = 'story'
          AND story.status IN ('to_do', 'in_progress', 'in_review', 'done')
          AND EXISTS (
            SELECT 1 FROM project_records AS parent
            WHERE parent.id = story.parent_id
              AND parent.record_type = 'task'
              AND parent.extra->>'scrum_role' = 'epic'
          )
    """))

    # Story in backlog with sprint parent → restore parent to epic via original_parent_id
    conn.execute(text("""
        UPDATE project_records AS story
        SET parent_id = (story.extra->>'original_parent_id')::uuid,
            extra = story.extra - 'original_parent_id'
        WHERE story.record_type = 'task'
          AND story.extra->>'scrum_role' = 'story'
          AND story.status = 'backlog'
          AND story.extra ? 'original_parent_id'
          AND EXISTS (
            SELECT 1 FROM project_records AS parent
            WHERE parent.id = story.parent_id
              AND parent.record_type = 'sprint'
          )
    """))

    conn.execute(text("""
        UPDATE project_records AS story
        SET status = 'backlog'
        WHERE story.record_type = 'task'
          AND story.extra->>'scrum_role' = 'story'
          AND story.status = 'backlog'
          AND EXISTS (
            SELECT 1 FROM project_records AS parent
            WHERE parent.id = story.parent_id
              AND parent.record_type = 'sprint'
          )
    """))

    # Epic in active status without sprint_id but with stories in a sprint → set sprint_id
    conn.execute(text("""
        UPDATE project_records AS epic
        SET extra = jsonb_set(
            COALESCE(epic.extra, '{}'::jsonb),
            '{sprint_id}',
            to_jsonb(sprint_story.sprint_id::text),
            true
        )
        FROM (
            SELECT DISTINCT
                (story.extra->>'original_parent_id') AS epic_id,
                story.parent_id AS sprint_id,
                story.project_id
            FROM project_records AS story
            JOIN project_records AS sprint ON sprint.id = story.parent_id
            WHERE story.record_type = 'task'
              AND story.extra->>'scrum_role' = 'story'
              AND sprint.record_type = 'sprint'
              AND story.extra ? 'original_parent_id'
        ) AS sprint_story
        WHERE epic.id::text = sprint_story.epic_id
          AND epic.project_id = sprint_story.project_id
          AND epic.record_type = 'task'
          AND epic.extra->>'scrum_role' = 'epic'
          AND epic.status IN ('to_do', 'in_progress', 'in_review', 'done')
          AND NOT (epic.extra ? 'sprint_id')
    """))


def downgrade() -> None:
    pass
