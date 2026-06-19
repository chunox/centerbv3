"""Borrado de proyecto con reportes aprobados (feature generada)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import Project, User
from app.services.deletions import delete_project
from app.services.feature_reports import apply_report_action
from app.services.records.repository import create_record, get_field
from tests.conftest import auth_headers
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org
from tests.record_helpers import create_milestone_record, create_report_record


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


def _seed_with_approved_report(session: Session):
    pm_id = uuid4()
    cliente_id = uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@del.test", password_hash="x"),
            User(id=cliente_id, nombre="Cli", email="cli@del.test", password_hash="x"),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
    project = create_project_for_org(
        session, pm_id, org, nombre="Demo", tipo="con_cliente"
    )
    add_member_with_slug(session, project, cliente_id, "cliente")
    milestone = create_milestone_record(session, project, created_by=pm_id)
    original = create_record(
        session,
        project,
        entity_type="feature",
        titulo="Login",
        created_by=pm_id,
        parent_id=milestone.id,
        estado="completado",
        data={"tipo": "desarrollo", "prioridad": "media", "bloqueada": False},
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
    )
    report = create_report_record(
        session,
        project,
        original,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Crash",
    )
    session.commit()

    apply_report_action(
        session, report, original, project, milestone, action="aprobar", actor_user_id=pm_id
    )
    session.commit()
    session.refresh(report)
    assert get_field(report, "generated_feature_id") is not None
    return project, pm_id


def test_delete_project_con_reporte_aprobado(db_session: Session):
    project, pm_id = _seed_with_approved_report(db_session)

    delete_project(db_session, project, actor_user_id=pm_id)
    db_session.commit()

    assert db_session.get(Project, project.id) is None


@pytest.fixture
def api_client(db_session: Session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_delete_project_api_con_reporte_aprobado(db_session: Session, api_client: TestClient):
    project, pm_id = _seed_with_approved_report(db_session)

    response = api_client.delete(
        f"/api/v1/projects/{project.id}",
        headers=auth_headers(pm_id, project.organization_id),
    )
    assert response.status_code == 204
    assert db_session.get(Project, project.id) is None
