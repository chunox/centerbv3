"""Borrado de proyecto con reportes aprobados (feature generada)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import Feature, FeatureReport, Milestone, Project, ProjectMember, User
from app.services.deletions import delete_project
from app.services.feature_reports import apply_report_action
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
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="Demo",
        tipo="con_cliente",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    session.add_all(
        [
            ProjectMember(project_id=project.id, user_id=pm_id, rol="pm"),
            ProjectMember(project_id=project.id, user_id=cliente_id, rol="cliente"),
        ]
    )
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
    original = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Login",
        tipo="desarrollo",
        estado="completado",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(original)
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Crash",
        estado="pendiente",
    )
    session.add(report)
    session.commit()

    apply_report_action(
        session, report, original, project, milestone, action="aprobar", actor_user_id=pm_id
    )
    session.commit()
    session.refresh(report)
    assert report.generated_feature_id is not None
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
        params={"actor_user_id": str(pm_id)},
    )
    assert response.status_code == 204
    assert db_session.get(Project, project.id) is None
