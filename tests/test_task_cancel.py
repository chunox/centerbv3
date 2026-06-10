"""Cancelación individual de tareas por Dev."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.entities import Base
from app.services.features import load_active_tasks
from app.services.tasks import move_task
from tests.test_features_workflow import _seed_project


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


def test_dev_can_cancel_active_task(db_session: Session):
    project, feature, _, _, dev_id, _ = _seed_project(db_session)
    task = load_active_tasks(db_session, feature.id)[0]

    move_task(
        db_session,
        task,
        feature,
        project,
        nuevo_estado="cancel",
        actor_user_id=dev_id,
    )

    assert task.estado == "cancel"


def test_cannot_cancel_completed_task(db_session: Session):
    project, feature, _, _, dev_id, _ = _seed_project(db_session)
    task = load_active_tasks(db_session, feature.id)[0]
    for estado in ("to_do", "in_progress", "ready_for_test", "completed"):
        move_task(
            db_session,
            task,
            feature,
            project,
            nuevo_estado=estado,
            actor_user_id=dev_id,
        )

    with pytest.raises(HTTPException) as exc:
        move_task(
            db_session,
            task,
            feature,
            project,
            nuevo_estado="cancel",
            actor_user_id=dev_id,
        )
    assert exc.value.status_code == 409
    assert "cancel" in exc.value.detail.lower()
