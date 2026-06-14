"""Tests transición cancel en workflow de tareas."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import User
from app.services.records.repository import create_record
from app.services.tasks import move_task
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org
from tests.record_helpers import create_feature_record, create_milestone_record


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
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(
        db_session,
        project,
        milestone,
        created_by=pm_id,
        nombre="F1",
        with_default_task=False,
    )
    feature.estado = "en_progreso"
    task = create_record(
        db_session,
        project,
        entity_type="task",
        titulo="T1",
        created_by=pm_id,
        parent_id=feature.id,
        estado="in_progress",
    )
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
