"""Tests workflow milestone: sync y cancelar."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Feature, Milestone, Project, User
from app.services.milestones import (
    cancel_milestone_cascade,
    compute_milestone_target_state,
    sync_milestone_state,
)
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


def _seed(db_session: Session):
    pm_id = uuid4()
    db_session.add(
        User(id=pm_id, nombre="PM", email="pm@mil.test", password_hash="x")
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org, tipo="interno")
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        estado="pendiente",
        created_by=pm_id,
    )
    db_session.add(milestone)
    db_session.commit()
    return project, milestone, pm_id


def test_compute_milestone_target_en_progreso(db_session: Session):
    project, milestone, pm_id = _seed(db_session)
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
    db_session.commit()
    assert (
        compute_milestone_target_state(milestone, [feature], project=project)
        == "en_progreso"
    )


def test_sync_milestone_via_workflow(db_session: Session):
    project, milestone, pm_id = _seed(db_session)
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
    db_session.commit()
    changed = sync_milestone_state(
        db_session, milestone, project, actor_user_id=pm_id
    )
    assert changed is True
    assert milestone.estado == "en_progreso"


def test_cancel_milestone_cascade_via_workflow(db_session: Session):
    project, milestone, pm_id = _seed(db_session)
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="F1",
        tipo="desarrollo",
        estado="pendiente",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    db_session.add(feature)
    db_session.commit()
    cancel_milestone_cascade(
        db_session, milestone, project, actor_user_id=pm_id
    )
    db_session.commit()
    assert milestone.estado == "cancelado"
    assert feature.estado == "cancelado"
