"""Tests de hub_entries — centro del proyecto."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import HubEntry, ProjectMember
from app.services.auth_tokens import create_access_token
from tests.org_helpers import create_organization, create_project_for_org, create_user


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


def _auth_headers(user_id, org_id):
    token = create_access_token(user_id=user_id, organization_id=org_id)
    return {"Authorization": f"Bearer {token}"}


def _seed_project(session: Session):
    pm = create_user(session, email="pm@hub.test")
    dev = create_user(session, email="dev@hub.test")
    qa = create_user(session, email="qa@hub.test")
    org = create_organization(session, owner_id=pm.id)
    project = create_project_for_org(session, pm.id, org)
    session.add(ProjectMember(project_id=project.id, user_id=dev.id, rol="dev"))
    session.add(ProjectMember(project_id=project.id, user_id=qa.id, rol="qa"))
    session.commit()
    return pm, dev, qa, org, project


def test_dev_can_create_update(api_client: TestClient, db_session: Session):
    pm, dev, _qa, org, project = _seed_project(db_session)
    resp = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "author_id": str(dev.id),
            "tipo": "update",
            "contenido": "Avance en login OAuth",
            "visibilidad": "publico",
        },
        headers=_auth_headers(dev.id, org.id),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["tipo"] == "update"
    assert data["author_nombre"] == dev.nombre
    assert data["contenido"] == "Avance en login OAuth"


def test_note_requires_title(api_client: TestClient, db_session: Session):
    pm, dev, _qa, org, project = _seed_project(db_session)
    resp = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "author_id": str(pm.id),
            "tipo": "note",
            "contenido": "Contenido de la nota",
            "visibilidad": "publico",
        },
        headers=_auth_headers(pm.id, org.id),
    )
    assert resp.status_code == 422


def test_qa_cannot_create(api_client: TestClient, db_session: Session):
    _pm, _dev, qa, org, project = _seed_project(db_session)
    resp = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "author_id": str(qa.id),
            "tipo": "update",
            "contenido": "Intento QA",
            "visibilidad": "publico",
        },
        headers=_auth_headers(qa.id, org.id),
    )
    assert resp.status_code == 403


def test_interno_hidden_from_list_filter(api_client: TestClient, db_session: Session):
    pm, dev, qa, org, project = _seed_project(db_session)
    api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "author_id": str(pm.id),
            "tipo": "update",
            "contenido": "Público",
            "visibilidad": "publico",
        },
        headers=_auth_headers(pm.id, org.id),
    )
    api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "author_id": str(pm.id),
            "tipo": "update",
            "contenido": "Interno",
            "visibilidad": "interno",
        },
        headers=_auth_headers(pm.id, org.id),
    )
    resp = api_client.get(
        f"/api/v1/projects/{project.id}/hub-entries"
        f"?viewer_user_id={qa.id}&viewer_rol=qa",
        headers=_auth_headers(qa.id, org.id),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp_dev = api_client.get(
        f"/api/v1/projects/{project.id}/hub-entries"
        f"?viewer_user_id={dev.id}&viewer_rol=dev&tipo=update",
        headers=_auth_headers(dev.id, org.id),
    )
    assert len(resp_dev.json()) == 2


def test_author_can_edit_own_entry(api_client: TestClient, db_session: Session):
    pm, dev, _qa, org, project = _seed_project(db_session)
    created = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "author_id": str(dev.id),
            "tipo": "update",
            "contenido": "Original",
            "visibilidad": "publico",
        },
        headers=_auth_headers(dev.id, org.id),
    ).json()
    resp = api_client.patch(
        f"/api/v1/projects/{project.id}/hub-entries/{created['id']}",
        json={"actor_user_id": str(dev.id), "contenido": "Editado"},
        headers=_auth_headers(dev.id, org.id),
    )
    assert resp.status_code == 200
    assert resp.json()["contenido"] == "Editado"


def test_pm_can_delete_any_entry(api_client: TestClient, db_session: Session):
    pm, dev, _qa, org, project = _seed_project(db_session)
    created = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "author_id": str(dev.id),
            "tipo": "update",
            "contenido": "Borrar",
            "visibilidad": "publico",
        },
        headers=_auth_headers(dev.id, org.id),
    ).json()
    resp = api_client.delete(
        f"/api/v1/projects/{project.id}/hub-entries/{created['id']}"
        f"?actor_user_id={pm.id}",
        headers=_auth_headers(pm.id, org.id),
    )
    assert resp.status_code == 204
    assert db_session.get(HubEntry, created["id"]) is None


def test_closed_project_blocks_create(api_client: TestClient, db_session: Session):
    pm, dev, _qa, org, project = _seed_project(db_session)
    project.estado = "cerrado"
    db_session.commit()
    resp = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "author_id": str(dev.id),
            "tipo": "update",
            "contenido": "No permitido",
            "visibilidad": "publico",
        },
        headers=_auth_headers(dev.id, org.id),
    )
    assert resp.status_code == 409
