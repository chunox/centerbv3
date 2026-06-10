"""Vertical slice: rol custom con capacidades parciales."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.domain.capabilities import KANBAN_TASK_MOVE, SCOPE_FEATURE_CREATE
from app.models.entities import Feature, Milestone, ProjectMember, Task, User
from app.services.project_roles import assign_member_role, create_custom_role
from app.services.tasks import move_task
from app.services.workflow.capabilities import get_effective_capabilities, user_has_capability
from tests.org_helpers import create_project_for_org, create_user


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_feature_task(session: Session, pm_id, project):
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
        nombre="API",
        tipo="desarrollo",
        estado="en_progreso",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(feature)
    task = Task(
        id=uuid4(),
        feature_id=feature.id,
        project_id=project.id,
        titulo="Tarea 1",
        estado="backlog",
        created_by=pm_id,
    )
    session.add(task)
    session.commit()
    return feature, task


def test_arquitecto_scope_without_kanban_move(db_session: Session):
    pm = create_user(db_session, email="pm@arch.test")
    architect = create_user(db_session, email="arch@arch.test", nombre="Arquitecto")
    project = create_project_for_org(db_session, pm.id, add_pm_member=True)

    role = create_custom_role(
        db_session,
        project,
        slug="arquitecto",
        nombre="Arquitecto",
        capability_keys=[SCOPE_FEATURE_CREATE],
    )
    assign_member_role(db_session, project.id, architect.id, role.id)
    db_session.commit()

    caps = get_effective_capabilities(db_session, project.id, architect.id)
    assert SCOPE_FEATURE_CREATE in caps
    assert KANBAN_TASK_MOVE not in caps
    assert user_has_capability(db_session, project.id, architect.id, SCOPE_FEATURE_CREATE)
    assert not user_has_capability(db_session, project.id, architect.id, KANBAN_TASK_MOVE)


def test_arquitecto_cannot_move_task(db_session: Session):
    pm = create_user(db_session, email="pm2@arch.test")
    architect = create_user(db_session, email="arch2@arch.test")
    project = create_project_for_org(db_session, pm.id, add_pm_member=True)

    role = create_custom_role(
        db_session,
        project,
        slug="arquitecto",
        nombre="Arquitecto",
        capability_keys=[SCOPE_FEATURE_CREATE],
    )
    assign_member_role(db_session, project.id, architect.id, role.id)
    feature, task = _seed_feature_task(db_session, pm.id, project)

    with pytest.raises(HTTPException) as exc:
        move_task(
            db_session,
            task,
            feature,
            project,
            nuevo_estado="to_do",
            actor_user_id=architect.id,
        )
    assert exc.value.status_code == 403


def test_dev_can_move_task_with_kanban_capability(db_session: Session):
    pm = create_user(db_session, email="pm3@arch.test")
    dev = create_user(db_session, email="dev3@arch.test")
    project = create_project_for_org(db_session, pm.id, add_pm_member=True)

    from tests.org_helpers import add_member_with_slug

    add_member_with_slug(db_session, project, dev.id, "dev")
    feature, task = _seed_feature_task(db_session, pm.id, project)

    move_task(
        db_session,
        task,
        feature,
        project,
        nuevo_estado="to_do",
        actor_user_id=dev.id,
    )
    assert task.estado == "to_do"
