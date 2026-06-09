"""Tests de asignación múltiple en tareas."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    Feature,
    Milestone,
    Notification,
    Project,
    ProjectMember,
    Task,
    TaskStateTransition,
    User,
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
    for desde, hasta in (
        ("backlog", "to_do"),
        ("to_do", "in_progress"),
        ("in_progress", "ready_for_test"),
        ("ready_for_test", "completed"),
    ):
        session.add(
            TaskStateTransition(
                estado_desde=desde,
                estado_hasta=hasta,
                rol_permitido="dev",
            )
        )
    session.commit()
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
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="P",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    session.add_all(
        [
            ProjectMember(project_id=project.id, user_id=pm_id, rol="pm"),
            ProjectMember(project_id=project.id, user_id=dev_a, rol="dev"),
            ProjectMember(project_id=project.id, user_id=dev_b, rol="dev"),
            ProjectMember(project_id=project.id, user_id=dev_c, rol="dev"),
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
        estado="pendiente",
        created_by=pm_id,
    )
    session.add(milestone)
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Login",
        tipo="desarrollo",
        prioridad="media",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        estado="pendiente",
        created_by=pm_id,
    )
    session.add(feature)
    session.commit()
    return project, milestone, feature, dev_a, dev_b, dev_c


def test_create_task_with_multiple_assignees(db_session, api_client):
    project, milestone, feature, dev_a, dev_b, _ = _seed_three_devs(db_session)
    base = (
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}"
        f"/features/{feature.id}/tasks"
    )
    response = api_client.post(
        base,
        json={
            "titulo": "Multi",
            "created_by": str(dev_a),
            "asignado_ids": [str(dev_a), str(dev_b)],
        },
    )
    assert response.status_code == 201
    ids = response.json()["asignado_ids"]
    assert set(ids) == {str(dev_a), str(dev_b)}


def test_patch_adds_assignee_notifies_only_new(db_session, api_client):
    project, milestone, feature, dev_a, dev_b, dev_c = _seed_three_devs(db_session)
    base = (
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}"
        f"/features/{feature.id}/tasks"
    )
    create = api_client.post(
        base,
        json={
            "titulo": "T",
            "created_by": str(dev_a),
            "asignado_ids": [str(dev_a), str(dev_b)],
        },
    )
    task_id = create.json()["id"]

    response = api_client.patch(
        f"{base}/{task_id}",
        json={
            "actor_user_id": str(dev_a),
            "asignado_ids": [str(dev_a), str(dev_b), str(dev_c)],
        },
    )
    assert response.status_code == 200
    assert set(response.json()["asignado_ids"]) == {
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
    project, milestone, feature, dev_a, dev_b, dev_c = _seed_three_devs(db_session)
    base = (
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}"
        f"/features/{feature.id}/tasks"
    )
    create = api_client.post(
        base,
        json={
            "titulo": "T",
            "created_by": str(dev_a),
            "asignado_ids": [str(dev_a), str(dev_b), str(dev_c)],
        },
    )
    task_id = create.json()["id"]

    response = api_client.patch(
        f"{base}/{task_id}",
        json={
            "actor_user_id": str(dev_a),
            "asignado_ids": [str(dev_a)],
        },
    )
    assert response.status_code == 200
    assert response.json()["asignado_ids"] == [str(dev_a)]

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
    project, milestone, feature, dev_a, dev_b, _ = _seed_three_devs(db_session)
    base = (
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}"
        f"/features/{feature.id}/tasks"
    )
    create = api_client.post(
        base,
        json={
            "titulo": "T",
            "created_by": str(dev_a),
            "asignado_ids": [str(dev_b)],
        },
    )
    task_id = create.json()["id"]

    response = api_client.patch(
        f"{base}/{task_id}",
        json={"actor_user_id": str(dev_a), "asignado_ids": []},
    )
    assert response.status_code == 200
    assert response.json()["asignado_ids"] == []
