"""Tests de asignación múltiple en tareas."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import Notification, User
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org
from tests.record_helpers import create_feature_record, create_milestone_record


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


def _records_base(project_id) -> str:
    return f"/api/v1/projects/{project_id}/records"


def _seed_three_devs(session: Session):
    pm_id = uuid4()
    dev_a = uuid4()
    dev_b = uuid4()
    dev_c = uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@test.com", password_hash="x"),
            User(id=dev_a, nombre="Dev A", email="a@test.com", password_hash="x"),
            User(id=dev_b, nombre="Dev B", email="b@test.com", password_hash="x"),
            User(id=dev_c, nombre="Dev C", email="c@test.com", password_hash="x"),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
    project = create_project_for_org(session, pm_id, org)
    add_member_with_slug(session, project, dev_a, "dev")
    add_member_with_slug(session, project, dev_b, "dev")
    add_member_with_slug(session, project, dev_c, "dev")
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature = create_feature_record(
        session,
        project,
        milestone,
        created_by=pm_id,
        with_default_task=False,
    )
    session.commit()
    return project, feature, dev_a, dev_b, dev_c


def test_create_task_with_multiple_assignees(db_session, api_client):
    project, feature, dev_a, dev_b, _ = _seed_three_devs(db_session)
    base = _records_base(project.id)
    response = api_client.post(
        base,
        json={
            "actor_user_id": str(dev_a),
            "record_type": "task",
            "titulo": "Multi",
            "parent_id": str(feature.id),
            "assignee_ids": [str(dev_a), str(dev_b)],
        },
    )
    assert response.status_code == 201
    ids = response.json()["assignee_ids"]
    assert set(ids) == {str(dev_a), str(dev_b)}


def test_patch_adds_assignee_notifies_only_new(db_session, api_client):
    project, feature, dev_a, dev_b, dev_c = _seed_three_devs(db_session)
    base = _records_base(project.id)
    create = api_client.post(
        base,
        json={
            "actor_user_id": str(dev_a),
            "record_type": "task",
            "titulo": "T",
            "parent_id": str(feature.id),
            "assignee_ids": [str(dev_a), str(dev_b)],
        },
    )
    task_id = create.json()["id"]

    response = api_client.patch(
        f"{base}/{task_id}",
        json={
            "actor_user_id": str(dev_a),
            "assignee_ids": [str(dev_a), str(dev_b), str(dev_c)],
        },
    )
    assert response.status_code == 200
    assert set(response.json()["assignee_ids"]) == {
        str(dev_a),
        str(dev_b),
        str(dev_c),
    }

    notif_c = db_session.scalar(
        select(Notification).where(
            Notification.user_id == dev_c,
            Notification.tipo == "asignado",
        )
    )
    assert notif_c is not None

    notifs_b = list(
        db_session.scalars(
            select(Notification).where(
                Notification.user_id == dev_b,
                Notification.tipo == "asignado",
                Notification.entidad_id == UUID(task_id),
            )
        )
    )
    assert len(notifs_b) == 1


def test_patch_remove_assignee_no_notification_to_removed(db_session, api_client):
    project, feature, dev_a, dev_b, dev_c = _seed_three_devs(db_session)
    base = _records_base(project.id)
    create = api_client.post(
        base,
        json={
            "actor_user_id": str(dev_a),
            "record_type": "task",
            "titulo": "T",
            "parent_id": str(feature.id),
            "assignee_ids": [str(dev_a), str(dev_b), str(dev_c)],
        },
    )
    task_id = create.json()["id"]

    response = api_client.patch(
        f"{base}/{task_id}",
        json={
            "actor_user_id": str(dev_a),
            "assignee_ids": [str(dev_a)],
        },
    )
    assert response.status_code == 200
    assert response.json()["assignee_ids"] == [str(dev_a)]

    notifs_b = list(
        db_session.scalars(
            select(Notification).where(
                Notification.user_id == dev_b,
                Notification.tipo == "asignado",
                Notification.entidad_id == UUID(task_id),
            )
        )
    )
    assert len(notifs_b) == 1


def test_patch_empty_assignees(db_session, api_client):
    project, feature, dev_a, dev_b, _ = _seed_three_devs(db_session)
    base = _records_base(project.id)
    create = api_client.post(
        base,
        json={
            "actor_user_id": str(dev_a),
            "record_type": "task",
            "titulo": "T",
            "parent_id": str(feature.id),
            "assignee_ids": [str(dev_b)],
        },
    )
    task_id = create.json()["id"]

    response = api_client.patch(
        f"{base}/{task_id}",
        json={"actor_user_id": str(dev_a), "assignee_ids": []},
    )
    assert response.status_code == 200
    assert response.json()["assignee_ids"] == []
