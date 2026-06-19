"""Validación de estimacion_horas en records."""
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import Project, User
from app.services.packs import seed_project_from_pack
from app.services.records.field_validation import (
    _enforce_task_hour_fields,
    validate_record_data,
)
from tests.org_helpers import create_organization


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


def _seed_software_project(session: Session):
    pm_id = uuid4()
    org = create_organization(session, owner_id=pm_id)
    session.add(
        User(id=pm_id, email="pm@test.local", nombre="PM", password_hash="x")
    )
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        nombre="Software",
        estado="activo",
        created_by=pm_id,
        template_slug="t6_scrum_interno",
        pack_slug="software",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )
    session.add(project)
    session.flush()
    seed_project_from_pack(session, project, "software", template_slug="t6_scrum_interno")
    session.commit()
    return project


def test_enforce_task_hour_fields_rejects_negative():
    with pytest.raises(HTTPException) as exc:
        _enforce_task_hour_fields("task", {"estimacion_horas": -1})
    assert exc.value.status_code == 422
    assert ">= 0" in str(exc.value.detail)


def test_enforce_task_hour_fields_allows_zero_and_positive():
    assert _enforce_task_hour_fields("task", {"estimacion_horas": 0})[
        "estimacion_horas"
    ] == 0.0
    assert _enforce_task_hour_fields("task", {"estimacion_horas": 2.5})[
        "estimacion_horas"
    ] == 2.5


def test_validate_record_data_rejects_negative_estimacion_horas(db_session: Session):
    project = _seed_software_project(db_session)
    with pytest.raises(HTTPException) as exc:
        validate_record_data(
            db_session,
            project.id,
            "task",
            {"estimacion_horas": -3},
            partial=True,
        )
    assert exc.value.status_code == 422
    assert ">= 0" in str(exc.value.detail)
