"""Tests plantillas default de workflows y workbenches."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import User
from tests.conftest import auth_headers
from tests.org_helpers import add_member_with_slug, create_project_for_org, create_user


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
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _seed(db_session: Session):
    pm = create_user(db_session, email="pm@tpl.test")
    dev = create_user(db_session, email="dev@tpl.test")
    project = create_project_for_org(db_session, pm.id, add_pm_member=True)
    add_member_with_slug(db_session, project, dev.id, "dev")
    db_session.commit()
    return project, pm.id, dev.id


def test_get_workflow_template_pm(db_session: Session, api_client: TestClient):
    project, pm_id, _ = _seed(db_session)
    response = api_client.get(
        f"/api/v1/projects/{project.id}/workflow-templates/feature",
        headers=auth_headers(pm_id),
    )
    assert response.status_code == 200
    body = response.json()
    assert "states" in body
    assert "transitions" in body
    assert body.get("initial_state")


def test_get_workbench_template_pm(db_session: Session, api_client: TestClient):
    project, pm_id, _ = _seed(db_session)
    response = api_client.get(
        f"/api/v1/projects/{project.id}/workbench-template",
        headers=auth_headers(pm_id),
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 5
    keys = {wb["key"] for wb in body}
    assert "overview" in keys
    assert "kanban" in keys


def test_get_workflow_template_dev_forbidden(db_session: Session, api_client: TestClient):
    project, _, dev_id = _seed(db_session)
    response = api_client.get(
        f"/api/v1/projects/{project.id}/workflow-templates/feature",
        headers=auth_headers(dev_id),
    )
    assert response.status_code == 403
