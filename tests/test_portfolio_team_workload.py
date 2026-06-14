"""Tests GET /projects/pm-portfolio/team-workload."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import OrganizationMember
from app.services.auth_tokens import create_access_token
from app.services.records.generic_store import sync_assignees
from app.services.records.repository import create_record
from tests.org_helpers import create_user
from tests.record_helpers import create_feature_record, create_milestone_record, seed_project_with_roles


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


@pytest.fixture
def api_client(db_session: Session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _url() -> str:
    return "/api/v1/projects/pm-portfolio/team-workload"


def _auth_headers(user_id, org_id):
    token = create_access_token(user_id=user_id, organization_id=org_id)
    return {"Authorization": f"Bearer {token}"}


def _seed_one_project(db_session: Session):
    project, pm_id, dev_id, qa_id = seed_project_with_roles(db_session)
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(
        db_session,
        project,
        milestone,
        created_by=pm_id,
        with_default_task=False,
    )
    task = create_record(
        db_session,
        project,
        entity_type="task",
        titulo="Tarea portfolio",
        created_by=pm_id,
        parent_id=feature.id,
        estado="to_do",
    )
    return project, pm_id, dev_id, qa_id, feature, task


def test_portfolio_team_workload_aggregates_pm_projects(db_session, api_client):
    project, pm_id, dev_id, _, _, task = _seed_one_project(db_session)
    sync_assignees(db_session, task, [dev_id])
    db_session.commit()

    response = api_client.get(
        _url(),
        params={"organization_id": str(project.organization_id)},
        headers=_auth_headers(pm_id, project.organization_id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["totals"]["projects"] == 1
    assert data["totals"]["assignments"] == 1
    assert len(data["projects"]) == 1
    project_row = data["projects"][0]
    assert project_row["projectId"] == str(project.id)
    dev_row = next(m for m in project_row["members"] if m["user_id"] == str(dev_id))
    assert len(dev_row["items"]) == 1
    assert dev_row["items"][0]["project_nombre"] == project.nombre


def test_portfolio_team_workload_forbidden_without_org_membership(db_session, api_client):
    project, pm_id, _, _, _, _ = _seed_one_project(db_session)
    outsider = create_user(db_session, nombre="Out", email="out@test.com")
    db_session.commit()

    response = api_client.get(
        _url(),
        params={"organization_id": str(project.organization_id)},
        headers=_auth_headers(outsider.id, project.organization_id),
    )
    assert response.status_code == 403


def test_portfolio_team_workload_empty_when_not_pm(db_session, api_client):
    project, pm_id, dev_id, _, _, task = _seed_one_project(db_session)
    sync_assignees(db_session, task, [dev_id])
    db_session.add(
        OrganizationMember(
            organization_id=project.organization_id,
            user_id=dev_id,
            rol="member",
        )
    )
    db_session.commit()

    response = api_client.get(
        _url(),
        params={"organization_id": str(project.organization_id)},
        headers=_auth_headers(dev_id, project.organization_id),
    )
    assert response.status_code == 200
    assert response.json()["projects"] == []
