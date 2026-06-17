"""Tests métricas Scrum."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Project, ProjectRecord, User
from app.services.scrum_metrics import compute_sprint_completed_sp, sync_sprint_velocidad_real
from tests.org_helpers import create_organization


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


def test_sync_sprint_velocidad_real(db_session: Session):
    pm_id = uuid4()
    project_id = uuid4()
    org = create_organization(db_session, owner_id=pm_id)
    db_session.add(
        User(
            id=pm_id,
            email="pm@test.local",
            nombre="PM",
            password_hash="x",
        )
    )
    db_session.add(
        Project(
            id=project_id,
            nombre="Scrum Test",
            estado="activo",
            created_by=pm_id,
            organization_id=org.id,
            template_slug="t6_scrum_interno",
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )
    )
    sprint = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="milestone",
        titulo="Sprint 1",
        estado="en_progreso",
        created_by=pm_id,
        data={"velocidad_planeada": 20},
    )
    db_session.add(sprint)
    f_done = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="feature",
        parent_id=sprint.id,
        titulo="Done",
        estado="completado",
        created_by=pm_id,
        data={"story_points": "5"},
    )
    f_open = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="feature",
        parent_id=sprint.id,
        titulo="Open",
        estado="en_progreso",
        created_by=pm_id,
        data={"story_points": "8"},
    )
    db_session.add_all([f_done, f_open])
    db_session.commit()

    total = sync_sprint_velocidad_real(db_session, sprint, commit=True)
    assert total == 5
    assert sprint.data["velocidad_real"] == 5
    assert compute_sprint_completed_sp(db_session, project_id, sprint.id) == 5
