"""Integración — migración 0004 sincroniza status=blocked en datos legacy."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord, ProjectRecordBlocker
from tests.conftest import make_user, make_org, make_project, make_project_role, make_member


def _load_migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0004_scrum_blocked_status.py"
    spec = importlib.util.spec_from_file_location("migration_0004", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _scrum_project(db: Session):
    user = make_user(db, email="mig0004@test.demo", nombre="Mig User")
    org = make_org(db, user)
    project = make_project(
        db, org, user,
        pack_slug="software-scrum",
        template_slug="t6_scrum_interno",
        delivery_mode="scrum",
    )
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, user, role)
    db.flush()
    return project, user


def test_migration_0004_blocks_records_with_active_blocker(db: Session):
    project, user = _scrum_project(db)

    epic = ProjectRecord(
        project_id=str(project.id),
        record_type="task",
        title="Epic Mig",
        status="in_progress",
        extra={"scrum_role": "epic"},
        created_by=str(user.id),
    )
    db.add(epic)
    db.flush()

    story = ProjectRecord(
        project_id=str(project.id),
        record_type="task",
        parent_id=str(epic.id),
        title="Story Mig",
        status="in_progress",
        extra={"scrum_role": "story"},
        created_by=str(user.id),
    )
    db.add(story)
    db.flush()

    dev = ProjectRecord(
        project_id=str(project.id),
        record_type="task",
        parent_id=str(story.id),
        title="Dev Mig",
        status="to_do",
        extra={"scrum_role": "dev"},
        created_by=str(user.id),
    )
    db.add(dev)
    db.flush()

    db.add(
        ProjectRecordBlocker(
            project_id=str(project.id),
            record_id=str(story.id),
            description="Legacy blocker",
            created_by=str(user.id),
        )
    )
    db.commit()

    mod = _load_migration()
    with patch("alembic.op.get_bind", return_value=db.get_bind()):
        mod.upgrade()

    db.expire_all()
    story_after = db.query(ProjectRecord).filter(ProjectRecord.id == story.id).one()
    dev_after = db.query(ProjectRecord).filter(ProjectRecord.id == dev.id).one()

    assert story_after.status == "blocked"
    assert story_after.extra.get("status_before_block") == "in_progress"
    assert dev_after.status == "blocked"
    assert dev_after.extra.get("blocked_by_inheritance") is True
    assert dev_after.extra.get("status_before_block") == "to_do"


def test_migration_0004_fixes_backlog_story_under_sprint(db: Session):
    """Historias backlog con parent sprint vuelven a épica (SQLite + PostgreSQL)."""
    project, user = _scrum_project(db)

    epic = ProjectRecord(
        project_id=str(project.id),
        record_type="task",
        title="Epic Backlog Fix",
        status="backlog",
        extra={"scrum_role": "epic"},
        created_by=str(user.id),
    )
    db.add(epic)
    db.flush()

    sprint = ProjectRecord(
        project_id=str(project.id),
        record_type="sprint",
        title="Sprint Mig",
        status="activo",
        extra={},
        created_by=str(user.id),
    )
    db.add(sprint)
    db.flush()

    story = ProjectRecord(
        project_id=str(project.id),
        record_type="task",
        parent_id=str(sprint.id),
        title="Story Orphan Backlog",
        status="backlog",
        extra={
            "scrum_role": "story",
            "original_parent_id": str(epic.id),
        },
        created_by=str(user.id),
    )
    db.add(story)
    db.commit()

    mod = _load_migration()
    with patch("alembic.op.get_bind", return_value=db.get_bind()):
        mod.upgrade()

    db.expire_all()
    story_after = db.query(ProjectRecord).filter(ProjectRecord.id == story.id).one()
    assert story_after.parent_id == str(epic.id)
    assert "original_parent_id" not in (story_after.extra or {})
