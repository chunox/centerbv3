"""
Tests de comentarios — CRUD.
"""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _setup(db):
    user = make_user(db, email="pm_c@test.demo", nombre="PM Comments")
    org = make_org(db, user)
    project = make_project(db, org, user)
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, user, role)
    db.commit()
    return project, auth_headers(user), user


def _create_record(client, project_id, headers):
    res = client.post(
        f"/api/v1/projects/{project_id}/records",
        json={"record_type": "feature", "title": "Feature", "status": "pendiente"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_list_comments_empty(client: TestClient, db):
    project, headers, _ = _setup(db)
    record = _create_record(client, project.id, headers)
    res = client.get(f"/api/v1/projects/{project.id}/records/{record['id']}/comments", headers=headers)
    assert res.status_code == 200
    assert res.json() == []


def test_create_comment(client: TestClient, db):
    project, headers, _ = _setup(db)
    record = _create_record(client, project.id, headers)
    res = client.post(
        f"/api/v1/projects/{project.id}/records/{record['id']}/comments",
        json={"contenido": "Este es mi comentario"},
        headers=headers,
    )
    assert res.status_code == 201
    c = res.json()
    assert c["contenido"] == "Este es mi comentario"
    assert "id" in c


def test_update_own_comment(client: TestClient, db):
    project, headers, _ = _setup(db)
    record = _create_record(client, project.id, headers)
    comment = client.post(
        f"/api/v1/projects/{project.id}/records/{record['id']}/comments",
        json={"contenido": "Original"},
        headers=headers,
    ).json()
    res = client.patch(
        f"/api/v1/projects/{project.id}/comments/{comment['id']}",
        json={"contenido": "Editado"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["contenido"] == "Editado"


def test_update_other_comment_forbidden(client: TestClient, db):
    project, pm_headers, _ = _setup(db)
    record = _create_record(client, project.id, pm_headers)
    comment = client.post(
        f"/api/v1/projects/{project.id}/records/{record['id']}/comments",
        json={"contenido": "Original"},
        headers=pm_headers,
    ).json()

    other_user = make_user(db, email="other_c@test.demo", nombre="Other")
    role = db.query(__import__("app.models.entities", fromlist=["ProjectRole"]).ProjectRole).filter_by(project_id=project.id, slug="dev").first()
    if not role:
        role = make_project_role(db, project, slug="dev")
    make_member(db, project, other_user, role)
    db.commit()
    other_headers = auth_headers(other_user)

    res = client.patch(
        f"/api/v1/projects/{project.id}/comments/{comment['id']}",
        json={"contenido": "Hack"},
        headers=other_headers,
    )
    assert res.status_code == 403


def test_delete_own_comment(client: TestClient, db):
    project, headers, _ = _setup(db)
    record = _create_record(client, project.id, headers)
    comment = client.post(
        f"/api/v1/projects/{project.id}/records/{record['id']}/comments",
        json={"contenido": "A borrar"},
        headers=headers,
    ).json()
    res = client.delete(f"/api/v1/projects/{project.id}/comments/{comment['id']}", headers=headers)
    assert res.status_code == 204
