"""Tests de dependencias entre tareas."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import (
    Feature,
    Milestone,
    Project,
    ProjectMember,
    Task,
    TaskDependency,
    TaskStateTransition,
    User,
)
from app.services.task_dependencies import create_dependency, delete_dependency
from app.services.tasks import move_task
from tests.org_helpers import create_organization
from tests.test_features_workflow import _seed_task_transitions


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    _seed_task_transitions(session)
    for desde in ("backlog", "to_do", "in_progress", "ready_for_test"):
        session.add(
            TaskStateTransition(
                estado_desde=desde,
                estado_hasta="cancel",
                rol_permitido="dev",
            )
        )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _seed_project_with_two_features(session: Session):
    pm_id = uuid4()
    dev_id = uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@test.com", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev@test.com", password_hash="x"),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="Deps",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    session.add_all(
        [
            ProjectMember(project_id=project.id, user_id=pm_id, rol="pm"),
            ProjectMember(project_id=project.id, user_id=dev_id, rol="dev"),
        ]
    )
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        created_by=pm_id,
    )
    session.add(milestone)
    feature_a = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Feature A",
        tipo="desarrollo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    feature_b = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Feature B",
        tipo="desarrollo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add_all([feature_a, feature_b])
    task_a = Task(
        id=uuid4(),
        feature_id=feature_a.id,
        project_id=project.id,
        titulo="Tarea A",
        estado="in_progress",
        created_by=dev_id,
    )
    task_b = Task(
        id=uuid4(),
        feature_id=feature_b.id,
        project_id=project.id,
        titulo="Tarea B",
        estado="backlog",
        created_by=dev_id,
    )
    session.add_all([task_a, task_b])
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
    assert dep.task_id == task_b.id
    assert dep.depends_on_task_id == task_a.id


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
    assert db_session.get(TaskDependency, dep.id) is None


def test_feature_blocked_still_blocks_move(db_session: Session):
    project, fa, fb, task_a, task_b, dev_id = _seed_project_with_two_features(
        db_session
    )
    fb.bloqueada = True
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
