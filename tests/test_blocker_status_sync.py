"""Tests unitarios — sync status=blocked (F1)."""
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.domain.scrum.states import EXTRA_BLOCKED_BY_INHERITANCE, EXTRA_STATUS_BEFORE_BLOCK
from app.models.entities import ProjectRecord, ProjectRecordBlocker
from app.services.blockers import (
    apply_block_to_record,
    cascade_block_to_descendants,
    has_blocked_descendant,
    has_own_active_blocker,
    restore_record_after_unblock,
    sync_block_on_create,
    sync_unblock_on_resolve,
)
from tests.conftest import make_org, make_project, make_user


def _scrum_project(db: Session):
    user = make_user(db, email="block_sync@test.demo", nombre="Block Sync")
    org = make_org(db, user)
    project = make_project(
        db, org, user,
        pack_slug="software-scrum",
        template_slug="t6_scrum_interno",
        delivery_mode="scrum",
    )
    return project, user


def _task(db: Session, project, user, title: str, *, parent_id=None, status="in_progress", role="story"):
    record = ProjectRecord(
        project_id=project.id,
        record_type="task",
        title=title,
        status=status,
        parent_id=parent_id,
        extra={"scrum_role": role},
        created_by=user.id,
    )
    db.add(record)
    db.flush()
    return record


def _add_blocker(db: Session, record: ProjectRecord, user_id) -> ProjectRecordBlocker:
    blocker = ProjectRecordBlocker(
        project_id=record.project_id,
        record_id=record.id,
        description="test block",
        created_by=user_id,
    )
    db.add(blocker)
    db.flush()
    return blocker


def test_apply_block_saves_status_before_block(db: Session):
    project, user = _scrum_project(db)
    story = _task(db, project, user, "S1", status="in_progress")

    assert apply_block_to_record(story, inherited=False) is True
    assert story.status == "blocked"
    assert story.extra[EXTRA_STATUS_BEFORE_BLOCK] == "in_progress"
    assert EXTRA_BLOCKED_BY_INHERITANCE not in story.extra


def test_apply_block_skips_done(db: Session):
    project, user = _scrum_project(db)
    story = _task(db, project, user, "Done", status="done")

    assert apply_block_to_record(story, inherited=False) is False
    assert story.status == "done"


def test_cascade_block_to_descendants(db: Session):
    project, user = _scrum_project(db)
    story = _task(db, project, user, "Parent", status="in_progress")
    dev = _task(db, project, user, "Dev", parent_id=story.id, status="to_do", role="dev")
    done_dev = _task(db, project, user, "Dev Done", parent_id=story.id, status="done", role="dev")

    changed = cascade_block_to_descendants(db, str(project.id), str(story.id))
    assert len(changed) == 1
    assert dev.status == "blocked"
    assert dev.extra.get(EXTRA_BLOCKED_BY_INHERITANCE) is True
    assert done_dev.status == "done"


def test_sync_block_on_create_with_blocker_row(db: Session):
    project, user = _scrum_project(db)
    story = _task(db, project, user, "Blocked", status="to_do")
    dev = _task(db, project, user, "Child", parent_id=story.id, status="in_progress", role="dev")
    _add_blocker(db, story, user.id)

    changed = sync_block_on_create(db, story)
    assert story in changed
    assert story.status == "blocked"
    assert dev.status == "blocked"


def test_restore_after_resolve_blocker(db: Session):
    project, user = _scrum_project(db)
    story = _task(db, project, user, "Restore", status="in_progress")
    apply_block_to_record(story, inherited=False)
    blocker = _add_blocker(db, story, user.id)

    blocker.resolved_at = datetime.now(timezone.utc)
    db.flush()

    assert restore_record_after_unblock(db, story) is True
    assert story.status == "in_progress"
    assert EXTRA_STATUS_BEFORE_BLOCK not in (story.extra or {})


def test_sync_unblock_restores_inherited_children(db: Session):
    project, user = _scrum_project(db)
    epic = _task(db, project, user, "Epic", status="in_progress", role="epic")
    story = _task(db, project, user, "Story", parent_id=epic.id, status="to_do")
    _add_blocker(db, epic, user.id)
    sync_block_on_create(db, epic)

    epic_blocker = (
        db.query(ProjectRecordBlocker)
        .filter(ProjectRecordBlocker.record_id == epic.id)
        .first()
    )
    epic_blocker.resolved_at = datetime.now(timezone.utc)
    db.flush()

    sync_unblock_on_resolve(db, epic)
    assert epic.status == "in_progress"
    assert story.status == "to_do"


def test_has_blocked_descendant(db: Session):
    project, user = _scrum_project(db)
    epic = _task(db, project, user, "Epic", status="in_progress", role="epic")
    story = _task(db, project, user, "Story", parent_id=epic.id, status="blocked")

    assert has_blocked_descendant(db, epic) is True
    assert has_blocked_descendant(db, story) is False


def test_has_own_active_blocker(db: Session):
    project, user = _scrum_project(db)
    story = _task(db, project, user, "Own", status="to_do")
    assert has_own_active_blocker(db, story) is False
    _add_blocker(db, story, user.id)
    assert has_own_active_blocker(db, story) is True
