"""Tests endpoints añadidos: tasks PATCH, users, projects filter, comments @mention."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import AuditLog, Notification, Project, User
from app.services.records.repository import create_record
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
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _seed_kanban(session: Session):
    pm_id = uuid4()
    dev_id = uuid4()
    other_dev = uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@new.test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev@new.test", password_hash="x"),
            User(
                id=other_dev,
                nombre="Dev2",
                email="dev2@new.test",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
    project = create_project_for_org(session, pm_id, org, nombre="P")
    add_member_with_slug(session, project, dev_id, "dev")
    add_member_with_slug(session, project, other_dev, "dev")
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature = create_feature_record(
        session,
        project,
        milestone,
        created_by=pm_id,
        with_default_task=False,
    )
    task = create_record(
        session,
        project,
        entity_type="task",
        titulo="Tarea",
        created_by=dev_id,
        parent_id=feature.id,
        estado="backlog",
    )
    session.commit()
    return project, milestone, feature, task, pm_id, dev_id, other_dev


def test_patch_task_asignacion_y_notificacion(db_session: Session, api_client: TestClient):
    project, milestone, feature, task, _, dev_id, other_dev = _seed_kanban(
        db_session
    )

    response = api_client.patch(
        f"/api/v1/projects/{project.id}/records/{task.id}",
        json={
            "actor_user_id": str(dev_id),
            "titulo": "Tarea renombrada",
            "assignee_ids": [str(other_dev)],
        },
    )
    assert response.status_code == 200
    assert response.json()["titulo"] == "Tarea renombrada"
    assert response.json()["assignee_ids"] == [str(other_dev)]

    notif = db_session.scalar(
        select(Notification).where(
            Notification.user_id == other_dev,
            Notification.tipo == "asignado",
        )
    )
    assert notif is not None


def test_pm_no_puede_crear_tarea(db_session: Session, api_client: TestClient):
    project, milestone, feature, _, pm_id, _, _ = _seed_kanban(db_session)

    response = api_client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "actor_user_id": str(pm_id),
            "record_type": "task",
            "titulo": "Nueva",
            "parent_id": str(feature.id),
        },
    )
    assert response.status_code == 403


def test_dev_puede_crear_dependencia_entre_tareas(
    db_session: Session, api_client: TestClient
):
    project, _, feature, task, _, dev_id, _ = _seed_kanban(db_session)
    pred = create_record(
        db_session,
        project,
        entity_type="task",
        titulo="Predecesora",
        created_by=dev_id,
        parent_id=feature.id,
        estado="in_progress",
    )
    db_session.commit()

    response = api_client.post(
        f"/api/v1/projects/{project.id}/record-dependencies",
        json={
            "actor_user_id": str(dev_id),
            "predecessor_id": str(pred.id),
            "successor_id": str(task.id),
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["predecessor_id"] == str(pred.id)
    assert body["successor_id"] == str(task.id)

    list_response = api_client.get(
        f"/api/v1/projects/{project.id}/record-dependencies",
        params={"actor_user_id": str(dev_id)},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_list_projects_filtrado_por_miembro(db_session: Session, api_client: TestClient):
    project, _, _, _, _, dev_id, _ = _seed_kanban(db_session)
    other_org = create_organization(db_session, owner_id=dev_id)
    other = Project(
        id=uuid4(),
        organization_id=other_org.id,
        nombre="Otro",
        template_slug="t3_interno_clasico",
        pack_slug="software",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=dev_id,
    )
    db_session.add(other)
    db_session.commit()

    response = api_client.get(
        "/api/v1/projects", params={"user_id": str(dev_id)}
    )
    assert response.status_code == 200
    ids = {p["id"] for p in response.json()}
    assert str(project.id) in ids
    assert str(other.id) not in ids


def test_comentario_mencion_notifica(db_session: Session, api_client: TestClient):
    project, _, feature, _, _, dev_id, other_dev = _seed_kanban(db_session)

    response = api_client.post(
        "/api/v1/comments",
        json={
            "entidad_tipo": "feature",
            "entidad_id": str(feature.id),
            "user_id": str(dev_id),
            "contenido": f"Hola @{other_dev} revisa esto",
        },
    )
    assert response.status_code == 201

    notif = db_session.scalar(
        select(Notification).where(
            Notification.user_id == other_dev,
            Notification.tipo == "mencionado",
        )
    )
    assert notif is not None


def test_patch_y_delete_user(db_session: Session, api_client: TestClient):
    from app.services.auth_tokens import create_access_token

    user_id = uuid4()
    db_session.add(
        User(
            id=user_id,
            nombre="Temp",
            email="temp@new.test",
            password_hash="x",
        )
    )
    db_session.commit()

    token = create_access_token(user_id=user_id)
    response = api_client.patch(
        f"/api/v1/users/{user_id}",
        json={"nombre": "Actualizado"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["nombre"] == "Actualizado"

    response = api_client.delete(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204


def test_audit_logs_filtrados_por_rol_dev(
    db_session: Session, api_client: TestClient
):
    project, _, feature, task, _, dev_id, _ = _seed_kanban(db_session)
    db_session.add(
        AuditLog(
            project_id=project.id,
            user_id=dev_id,
            entidad_tipo="tarea",
            entidad_id=task.id,
            accion="estado_changed",
        )
    )
    db_session.add(
        AuditLog(
            project_id=project.id,
            user_id=dev_id,
            entidad_tipo="project",
            entidad_id=project.id,
            accion="updated",
        )
    )
    db_session.commit()

    response = api_client.get(
        f"/api/v1/projects/{project.id}/audit-logs",
        params={"viewer_user_id": str(dev_id)},
    )
    assert response.status_code == 200
    tipos = {row["entidad_tipo"] for row in response.json()}
    assert "tarea" in tipos
    assert "project" not in tipos
