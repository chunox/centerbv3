"""Tests de hub_entries — centro del proyecto."""

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.entities import HubEntry
from tests.conftest import auth_headers
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org, create_user


def _seed_project(session: Session):
    pm = create_user(session, email="pm@hub.test")
    dev = create_user(session, email="dev@hub.test")
    qa = create_user(session, email="qa@hub.test")
    org = create_organization(session, owner_id=pm.id)
    project = create_project_for_org(session, pm.id, org)
    add_member_with_slug(session, project, dev.id, "dev")
    add_member_with_slug(session, project, qa.id, "qa")
    session.commit()
    return pm, dev, qa, org, project


def test_dev_can_create_update(api_client: TestClient, db_session: Session):
    _pm, dev, _qa, _org, project = _seed_project(db_session)
    resp = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "tipo": "update",
            "contenido": "Avance en login OAuth",
        },
        headers=auth_headers(dev.id),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["tipo"] == "update"
    assert data["author_nombre"] == dev.nombre
    assert data["contenido"] == "Avance en login OAuth"


def test_note_requires_title(api_client: TestClient, db_session: Session):
    pm, _dev, _qa, org, project = _seed_project(db_session)
    resp = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "tipo": "note",
            "contenido": "Contenido de la nota",
        },
        headers=auth_headers(pm.id, org.id),
    )
    assert resp.status_code == 422


def test_qa_cannot_create(api_client: TestClient, db_session: Session):
    _pm, _dev, qa, _org, project = _seed_project(db_session)
    resp = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "tipo": "update",
            "contenido": "Intento QA",
        },
        headers=auth_headers(qa.id),
    )
    assert resp.status_code == 403


def test_interno_hidden_from_list_filter(api_client: TestClient, db_session: Session):
    pm, dev, qa, org, project = _seed_project(db_session)
    api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "tipo": "update",
            "contenido": "Público",
        },
        headers=auth_headers(pm.id, org.id),
    )
    api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "tipo": "update",
            "contenido": "Interno",
            "visible_roles": ["pm"],
        },
        headers=auth_headers(pm.id, org.id),
    )
    resp = api_client.get(
        f"/api/v1/projects/{project.id}/hub-entries",
        headers=auth_headers(qa.id),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp_dev = api_client.get(
        f"/api/v1/projects/{project.id}/hub-entries?tipo=update",
        headers=auth_headers(dev.id),
    )
    assert len(resp_dev.json()) == 1


def test_author_can_edit_own_entry(api_client: TestClient, db_session: Session):
    _pm, dev, _qa, _org, project = _seed_project(db_session)
    created = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "tipo": "update",
            "contenido": "Original",
        },
        headers=auth_headers(dev.id),
    ).json()
    resp = api_client.patch(
        f"/api/v1/projects/{project.id}/hub-entries/{created['id']}",
        json={"contenido": "Editado"},
        headers=auth_headers(dev.id),
    )
    assert resp.status_code == 200
    assert resp.json()["contenido"] == "Editado"


def test_pm_can_delete_any_entry(api_client: TestClient, db_session: Session):
    pm, dev, _qa, org, project = _seed_project(db_session)
    created = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "tipo": "update",
            "contenido": "Borrar",
        },
        headers=auth_headers(dev.id),
    ).json()
    resp = api_client.delete(
        f"/api/v1/projects/{project.id}/hub-entries/{created['id']}",
        headers=auth_headers(pm.id, org.id),
    )
    assert resp.status_code == 204
    assert db_session.get(HubEntry, UUID(created["id"])) is None


def test_closed_project_blocks_create(api_client: TestClient, db_session: Session):
    _pm, dev, _qa, _org, project = _seed_project(db_session)
    project.estado = "cerrado"
    db_session.commit()
    resp = api_client.post(
        f"/api/v1/projects/{project.id}/hub-entries",
        json={
            "tipo": "update",
            "contenido": "No permitido",
        },
        headers=auth_headers(dev.id),
    )
    assert resp.status_code == 409
