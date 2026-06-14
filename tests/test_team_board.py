"""Tests vista Equipo PM — team-board endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import ProjectRole, ProjectRoleCapability
from app.services.records.repository import create_record
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


def _team_board_url(project_id) -> str:
    return f"/api/v1/projects/{project_id}/team-board"


def _seed_task_on_feature(
    db_session: Session,
    *,
    assign_dev: bool = False,
):
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
        titulo="Implementar login",
        created_by=pm_id,
        parent_id=feature.id,
        estado="to_do",
    )
    if assign_dev:
        from app.services.records.generic_store import sync_assignees

        sync_assignees(db_session, task, [dev_id])
    db_session.commit()
    return project, pm_id, dev_id, qa_id, milestone, feature, task


def test_team_board_shows_assigned_task_for_dev(db_session, api_client):
    project, pm_id, dev_id, _, milestone, feature, task = _seed_task_on_feature(
        db_session, assign_dev=True
    )
    response = api_client.get(
        _team_board_url(project.id),
        params={"viewer_user_id": str(pm_id)},
    )
    assert response.status_code == 200
    data = response.json()
    dev_row = next(m for m in data["members"] if m["user_id"] == str(dev_id))
    assert len(dev_row["items"]) == 1
    item = dev_row["items"][0]
    assert item["record_id"] == str(task.id)
    assert item["record_type"] == "task"
    assert item["titulo"] == "Implementar login"
    assert item["estado"] == "to_do"
    assert item["estado_label"]
    assert item["parent_titulo"] == feature.titulo
    assert item["root_parent_titulo"] == milestone.titulo
    assert item["root_parent_id"] == str(milestone.id)


def test_team_board_member_without_assignments_has_empty_items(db_session, api_client):
    project, pm_id, dev_id, qa_id, _, _, _ = _seed_task_on_feature(
        db_session, assign_dev=True
    )
    response = api_client.get(
        _team_board_url(project.id),
        params={"viewer_user_id": str(pm_id)},
    )
    assert response.status_code == 200
    qa_row = next(m for m in response.json()["members"] if m["user_id"] == str(qa_id))
    assert qa_row["items"] == []
    assert qa_row["summary"]["total"] == 0


def test_team_board_unassigned_bucket(db_session, api_client):
    project, pm_id, dev_id, _, _, _, task = _seed_task_on_feature(db_session)
    response = api_client.get(
        _team_board_url(project.id),
        params={"viewer_user_id": str(pm_id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["totals"]["unassigned"] == 1
    assert len(data["unassigned"]) == 1
    assert data["unassigned"][0]["record_id"] == str(task.id)
    dev_row = next(m for m in data["members"] if m["user_id"] == str(dev_id))
    assert dev_row["items"] == []


def test_team_board_forbidden_without_workbench_team(db_session, api_client):
    project, pm_id, dev_id, _, _, _, _ = _seed_task_on_feature(
        db_session, assign_dev=True
    )
    dev_role = db_session.scalar(
        select(ProjectRole).where(
            ProjectRole.project_id == project.id,
            ProjectRole.slug == "dev",
        )
    )
    assert dev_role is not None
    team_cap = db_session.scalar(
        select(ProjectRoleCapability).where(
            ProjectRoleCapability.role_id == dev_role.id,
            ProjectRoleCapability.capability_key == "workbench.team",
        )
    )
    if team_cap:
        db_session.delete(team_cap)
        db_session.commit()

    pm_ok = api_client.get(
        _team_board_url(project.id),
        params={"viewer_user_id": str(pm_id)},
    )
    assert pm_ok.status_code == 200

    denied = api_client.get(
        _team_board_url(project.id),
        params={"viewer_user_id": str(dev_id)},
    )
    assert denied.status_code == 403
