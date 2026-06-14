"""Tests de sub-tareas."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import ProjectRecordDependency
from app.schemas.tasks import TaskSubtaskCreate
from app.services.records.repository import create_record, get_field, set_field
from app.services.task_dependencies import create_dependency
from app.services.tasks import create_subtask, move_task
from tests.record_helpers import (
    create_feature_record,
    create_milestone_record,
    seed_project_with_roles,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_project_with_parent_task(session: Session):
    project, pm_id, dev_id, _ = seed_project_with_roles(session)
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature = create_feature_record(
        session,
        project,
        milestone,
        created_by=pm_id,
        nombre="Feature A",
        with_default_task=False,
    )
    parent = create_record(
        session,
        project,
        entity_type="task",
        titulo="Tarea padre",
        created_by=dev_id,
        parent_id=feature.id,
        estado="backlog",
    )
    session.commit()
    return project, feature, parent, dev_id


def test_create_subtask_sets_parent_and_dependency(db_session: Session):
    project, feature, parent, dev_id = _seed_project_with_parent_task(db_session)
    child = create_subtask(
        db_session,
        parent,
        feature,
        project,
        TaskSubtaskCreate(titulo="Sub 1", actor_user_id=dev_id),
    )
    db_session.commit()

    assert get_field(child, "parent_task_id") == str(parent.id)
    assert child.parent_id == parent.parent_id
    dep = db_session.scalar(
        select(ProjectRecordDependency).where(
            ProjectRecordDependency.successor_id == parent.id,
            ProjectRecordDependency.predecessor_id == child.id,
        )
    )
    assert dep is not None


def test_parent_blocked_until_subtask_completed(db_session: Session):
    project, feature, parent, dev_id = _seed_project_with_parent_task(db_session)
    child = create_subtask(
        db_session,
        parent,
        feature,
        project,
        TaskSubtaskCreate(titulo="Sub 1", actor_user_id=dev_id),
    )
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        move_task(
            db_session,
            parent,
            feature,
            project,
            nuevo_estado="to_do",
            actor_user_id=dev_id,
        )
    assert exc.value.status_code == 409

    child.estado = "completed"
    db_session.flush()
    move_task(
        db_session,
        parent,
        feature,
        project,
        nuevo_estado="to_do",
        actor_user_id=dev_id,
    )
    assert parent.estado == "to_do"


def test_reject_subtask_when_parent_cancelled(db_session: Session):
    project, feature, parent, dev_id = _seed_project_with_parent_task(db_session)
    parent.estado = "cancel"
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        create_subtask(
            db_session,
            parent,
            feature,
            project,
            TaskSubtaskCreate(titulo="Sub 1", actor_user_id=dev_id),
        )
    assert exc.value.status_code == 409


def test_reject_subtask_when_feature_blocked(db_session: Session):
    project, feature, parent, dev_id = _seed_project_with_parent_task(db_session)
    set_field(feature, "bloqueada", True)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        create_subtask(
            db_session,
            parent,
            feature,
            project,
            TaskSubtaskCreate(titulo="Sub 1", actor_user_id=dev_id),
        )
    assert exc.value.status_code == 409


def test_nested_subtask_allowed(db_session: Session):
    project, feature, parent, dev_id = _seed_project_with_parent_task(db_session)
    child = create_subtask(
        db_session,
        parent,
        feature,
        project,
        TaskSubtaskCreate(titulo="Sub 1", actor_user_id=dev_id),
    )
    db_session.flush()

    grandchild = create_subtask(
        db_session,
        child,
        feature,
        project,
        TaskSubtaskCreate(titulo="Sub 2", actor_user_id=dev_id),
    )
    db_session.commit()

    assert get_field(grandchild, "parent_task_id") == str(child.id)
    dep = db_session.scalar(
        select(ProjectRecordDependency).where(
            ProjectRecordDependency.successor_id == child.id,
            ProjectRecordDependency.predecessor_id == grandchild.id,
        )
    )
    assert dep is not None
