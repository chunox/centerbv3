"""Tests transición cancel en workflow de tareas."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Feature, Milestone, Project, Task, User
from app.services.tasks import move_task
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org


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


def test_move_task_cancel_via_workflow(db_session: Session):
    pm_id = uuid4()
    dev_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@tc.test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev@tc.test", password_hash="x"),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org)
    add_member_with_slug(db_session, project, dev_id, "dev")
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
    db_session.add(milestone)
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="F1",
        tipo="desarrollo",
        estado="en_progreso",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    db_session.add(feature)
    task = Task(
        id=uuid4(),
        feature_id=feature.id,
        project_id=project.id,
        titulo="T1",
        estado="in_progress",
        created_by=pm_id,
    )
    db_session.add(task)
    db_session.commit()

    move_task(
        db_session,
        task,
        feature,
        project,
        nuevo_estado="cancel",
        actor_user_id=dev_id,
    )
    db_session.commit()
    assert task.estado == "cancel"
