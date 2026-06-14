"""Tests workflow milestone: sync y cancelar."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import User
from app.services.milestones import (
    cancel_milestone_cascade,
    compute_milestone_target_state,
    sync_milestone_state,
)
from app.services.records.repository import create_record
from tests.org_helpers import create_organization, create_project_for_org
from tests.record_helpers import create_milestone_record


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


def _seed(db_session: Session):
    pm_id = uuid4()
    db_session.add(
        User(id=pm_id, nombre="PM", email="pm@mil.test", password_hash="x")
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org, tipo="interno")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    db_session.commit()
    return project, milestone, pm_id


def _add_feature(session, project, milestone, pm_id, *, estado: str):
    return create_record(
        session,
        project,
        entity_type="feature",
        titulo="F1",
        created_by=pm_id,
        parent_id=milestone.id,
        estado=estado,
        data={"tipo": "desarrollo", "prioridad": "media", "bloqueada": False},
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
    )


def test_compute_milestone_target_en_progreso(db_session: Session):
    project, milestone, pm_id = _seed(db_session)
    feature = _add_feature(db_session, project, milestone, pm_id, estado="en_progreso")
    db_session.commit()
    assert (
        compute_milestone_target_state(milestone, [feature], project=project)
        == "en_progreso"
    )


def test_sync_milestone_via_workflow(db_session: Session):
    project, milestone, pm_id = _seed(db_session)
    feature = _add_feature(db_session, project, milestone, pm_id, estado="en_progreso")
    db_session.commit()
    changed = sync_milestone_state(
        db_session, milestone, project, actor_user_id=pm_id
    )
    assert changed is True
    assert milestone.estado == "en_progreso"


def test_cancel_milestone_cascade_via_workflow(db_session: Session):
    project, milestone, pm_id = _seed(db_session)
    feature = _add_feature(db_session, project, milestone, pm_id, estado="pendiente")
    db_session.commit()
    cancel_milestone_cascade(
        db_session, milestone, project, actor_user_id=pm_id
    )
    db_session.commit()
    assert milestone.estado == "cancelado"
    assert feature.estado == "cancelado"
