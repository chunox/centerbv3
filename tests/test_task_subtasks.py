"""Tests de sub-tareas."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
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
from app.schemas.tasks import TaskSubtaskCreate
from app.services.task_dependencies import create_dependency
from app.services.tasks import create_subtask, move_task
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


def _seed_project_with_parent_task(session: Session):
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
        nombre="Subtasks",
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
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Feature A",
        tipo="desarrollo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(feature)
    parent = Task(
        id=uuid4(),
        feature_id=feature.id,
        project_id=project.id,
        titulo="Tarea padre",
        estado="backlog",
        created_by=dev_id,
    )
    session.add(parent)
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

    assert child.parent_task_id == parent.id
    assert child.feature_id == parent.feature_id
    dep = db_session.scalar(
        select(TaskDependency).where(
            TaskDependency.task_id == parent.id,
            TaskDependency.depends_on_task_id == child.id,
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
    feature.bloqueada = True
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

    assert grandchild.parent_task_id == child.id
    dep = db_session.scalar(
        select(TaskDependency).where(
            TaskDependency.task_id == child.id,
            TaskDependency.depends_on_task_id == grandchild.id,
        )
    )
    assert dep is not None
