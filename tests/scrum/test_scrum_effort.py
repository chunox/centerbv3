"""Tests rollup de horas Scrum y sync de fechas."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Project, ProjectRecord, User
from app.services.records.repository import update_record_fields
from app.services.scrum_effort import (
    batch_feature_effort_hours,
    compute_feature_effort_hours,
    propagate_sprint_dates_to_features,
    sync_feature_dates_from_sprint,
)
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


def _scrum_project(db: Session, pm_id, project_id):
    org = create_organization(db, owner_id=pm_id)
    db.add(
        User(
            id=pm_id,
            email="pm@test.local",
            nombre="PM",
            password_hash="x",
        )
    )
    db.add(
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
    db.flush()


def test_compute_feature_effort_hours_sums_and_excludes_cancel(db_session: Session):
    pm_id = uuid4()
    project_id = uuid4()
    _scrum_project(db_session, pm_id, project_id)

    feature = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="feature",
        titulo="Historia",
        estado="pendiente",
        created_by=pm_id,
    )
    db_session.add(feature)
    db_session.add(
        ProjectRecord(
            id=uuid4(),
            project_id=project_id,
            record_type="task",
            parent_id=feature.id,
            titulo="T1",
            estado="to_do",
            created_by=pm_id,
            data={"estimacion_horas": 4},
        )
    )
    db_session.add(
        ProjectRecord(
            id=uuid4(),
            project_id=project_id,
            record_type="task",
            parent_id=feature.id,
            titulo="T2",
            estado="cancel",
            created_by=pm_id,
            data={"estimacion_horas": 8},
        )
    )
    db_session.add(
        ProjectRecord(
            id=uuid4(),
            project_id=project_id,
            record_type="task",
            parent_id=feature.id,
            titulo="T3",
            estado="in_progress",
            created_by=pm_id,
            data={"estimacion_horas": 2.5},
        )
    )
    db_session.commit()

    assert compute_feature_effort_hours(db_session, feature.id) == 6.5


def test_batch_feature_effort_hours(db_session: Session):
    pm_id = uuid4()
    project_id = uuid4()
    _scrum_project(db_session, pm_id, project_id)

    f1 = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="feature",
        titulo="F1",
        estado="pendiente",
        created_by=pm_id,
    )
    f2 = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="feature",
        titulo="F2",
        estado="pendiente",
        created_by=pm_id,
    )
    db_session.add_all([f1, f2])
    db_session.add(
        ProjectRecord(
            id=uuid4(),
            project_id=project_id,
            record_type="task",
            parent_id=f1.id,
            titulo="T",
            estado="to_do",
            created_by=pm_id,
            data={"estimacion_horas": 3},
        )
    )
    db_session.commit()

    result = batch_feature_effort_hours(db_session, project_id, [f1.id, f2.id])
    assert result[f1.id] == 3.0
    assert result[f2.id] == 0.0


def test_sync_feature_dates_from_sprint(db_session: Session):
    pm_id = uuid4()
    project_id = uuid4()
    _scrum_project(db_session, pm_id, project_id)

    sprint = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="sprint",
        titulo="Sprint 1",
        estado="en_progreso",
        created_by=pm_id,
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 3, 14),
    )
    feature = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="feature",
        titulo="Historia",
        estado="pendiente",
        created_by=pm_id,
        data={"sprint_id": str(sprint.id)},
    )
    db_session.add_all([sprint, feature])
    db_session.commit()

    changed = sync_feature_dates_from_sprint(db_session, feature, sprint)
    assert changed is True
    assert feature.fecha_inicio == date(2026, 3, 1)
    assert feature.fecha_fin == date(2026, 3, 14)


def test_propagate_sprint_dates_to_features(db_session: Session):
    pm_id = uuid4()
    project_id = uuid4()
    _scrum_project(db_session, pm_id, project_id)

    sprint = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="sprint",
        titulo="Sprint 1",
        estado="en_progreso",
        created_by=pm_id,
        fecha_inicio=date(2026, 4, 1),
        fecha_fin=date(2026, 4, 14),
        data={"tipo": "sprint"},
    )
    f1 = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="task",
        parent_id=sprint.id,
        titulo="H1",
        estado="pendiente",
        created_by=pm_id,
        data={"scrum_role": "story"},
    )
    f2 = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="task",
        parent_id=sprint.id,
        titulo="H2",
        estado="en_progreso",
        created_by=pm_id,
        data={"scrum_role": "story"},
    )
    db_session.add_all([sprint, f1, f2])
    db_session.commit()

    update_record_fields(
        db_session,
        sprint,
        fecha_inicio=date(2026, 5, 1),
        fecha_fin=date(2026, 5, 15),
    )
    count = propagate_sprint_dates_to_features(db_session, sprint)
    assert count == 2
    assert f1.fecha_inicio == date(2026, 5, 1)
    assert f2.fecha_fin == date(2026, 5, 15)
