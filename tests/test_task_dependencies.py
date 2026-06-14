"""Tests de dependencias entre tareas."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import ProjectRecordDependency
from app.services.records.repository import create_record, set_field
from app.services.task_dependencies import create_dependency, delete_dependency
from app.services.tasks import move_task
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


def _seed_project_with_two_features(session: Session):
    project, pm_id, dev_id, _ = seed_project_with_roles(session)
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature_a = create_feature_record(
        session,
        project,
        milestone,
        created_by=pm_id,
        nombre="Feature A",
        with_default_task=False,
    )
    feature_b = create_feature_record(
        session,
        project,
        milestone,
        created_by=pm_id,
        nombre="Feature B",
        with_default_task=False,
    )
    task_a = create_record(
        session,
        project,
        entity_type="task",
        titulo="Tarea A",
        created_by=dev_id,
        parent_id=feature_a.id,
        estado="in_progress",
    )
    task_b = create_record(
        session,
        project,
        entity_type="task",
        titulo="Tarea B",
        created_by=dev_id,
        parent_id=feature_b.id,
        estado="backlog",
    )
    session.commit()
    return project, feature_a, feature_b, task_a, task_b, dev_id


def test_create_cross_feature_dependency(db_session: Session):
    project, fa, fb, task_a, task_b, dev_id = _seed_project_with_two_features(
        db_session
    )
    dep = create_dependency(
        db_session,
        project,
        task_b,
        task_a,
        actor_user_id=dev_id,
    )
    db_session.commit()
    assert dep.successor_id == task_b.id
    assert dep.predecessor_id == task_a.id


def test_reject_self_loop(db_session: Session):
    project, _, _, task_a, _, dev_id = _seed_project_with_two_features(db_session)
    with pytest.raises(HTTPException) as exc:
        create_dependency(
            db_session,
            project,
            task_a,
            task_a,
            actor_user_id=dev_id,
        )
    assert exc.value.status_code == 400


def test_reject_cycle(db_session: Session):
    project, _, _, task_a, task_b, dev_id = _seed_project_with_two_features(
        db_session
    )
    create_dependency(
        db_session, project, task_b, task_a, actor_user_id=dev_id
    )
    db_session.flush()
    with pytest.raises(HTTPException) as exc:
        create_dependency(
            db_session, project, task_a, task_b, actor_user_id=dev_id
        )
    assert exc.value.status_code == 409


def test_move_blocked_by_unsatisfied_predecessor(db_session: Session):
    project, fa, fb, task_a, task_b, dev_id = _seed_project_with_two_features(
        db_session
    )
    create_dependency(
        db_session, project, task_b, task_a, actor_user_id=dev_id
    )
    db_session.flush()
    with pytest.raises(HTTPException) as exc:
        move_task(
            db_session,
            task_b,
            fb,
            project,
            nuevo_estado="to_do",
            actor_user_id=dev_id,
        )
    assert exc.value.status_code == 409


def test_move_allowed_when_predecessor_completed(db_session: Session):
    project, fa, fb, task_a, task_b, dev_id = _seed_project_with_two_features(
        db_session
    )
    create_dependency(
        db_session, project, task_b, task_a, actor_user_id=dev_id
    )
    task_a.estado = "completed"
    db_session.flush()
    move_task(
        db_session,
        task_b,
        fb,
        project,
        nuevo_estado="to_do",
        actor_user_id=dev_id,
    )
    assert task_b.estado == "to_do"


def test_move_allowed_when_predecessor_cancelled(db_session: Session):
    project, fa, fb, task_a, task_b, dev_id = _seed_project_with_two_features(
        db_session
    )
    create_dependency(
        db_session, project, task_b, task_a, actor_user_id=dev_id
    )
    task_a.estado = "cancel"
    db_session.flush()
    move_task(
        db_session,
        task_b,
        fb,
        project,
        nuevo_estado="to_do",
        actor_user_id=dev_id,
    )
    assert task_b.estado == "to_do"


def test_move_to_cancel_allowed_with_unsatisfied_deps(db_session: Session):
    project, fa, fb, task_a, task_b, dev_id = _seed_project_with_two_features(
        db_session
    )
    create_dependency(
        db_session, project, task_b, task_a, actor_user_id=dev_id
    )
    task_b.estado = "to_do"
    db_session.flush()
    move_task(
        db_session,
        task_b,
        fb,
        project,
        nuevo_estado="cancel",
        actor_user_id=dev_id,
    )
    assert task_b.estado == "cancel"


def test_delete_dependency(db_session: Session):
    project, _, _, task_a, task_b, dev_id = _seed_project_with_two_features(
        db_session
    )
    dep = create_dependency(
        db_session, project, task_b, task_a, actor_user_id=dev_id
    )
    db_session.flush()
    delete_dependency(
        db_session, project, dep, actor_user_id=dev_id
    )
    db_session.flush()
    assert db_session.get(ProjectRecordDependency, dep.id) is None


def test_feature_blocked_still_blocks_move(db_session: Session):
    project, fa, fb, task_a, task_b, dev_id = _seed_project_with_two_features(
        db_session
    )
    set_field(fb, "bloqueada", True)
    db_session.flush()
    with pytest.raises(HTTPException) as exc:
        move_task(
            db_session,
            task_b,
            fb,
            project,
            nuevo_estado="to_do",
            actor_user_id=dev_id,
        )
    assert exc.value.status_code == 409
    assert "bloqueada" in exc.value.detail.lower()
