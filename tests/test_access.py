"""
Tests de acceso — guards 403 cuando no es miembro.
"""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def test_non_member_cannot_list_records(client: TestClient, db):
    owner = make_user(db, email="owner_a@test.demo", nombre="Owner A")
    org = make_org(db, owner)
    project = make_project(db, org, owner)
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, owner, role)
    db.commit()

    outsider = make_user(db, email="outsider_a@test.demo", nombre="Outsider A")
    db.commit()
    headers = auth_headers(outsider)

    res = client.get(f"/api/v1/projects/{project.id}/records", headers=headers)
    assert res.status_code == 403


def test_non_member_cannot_create_record(client: TestClient, db):
    owner = make_user(db, email="owner_b@test.demo", nombre="Owner B")
    org = make_org(db, owner)
    project = make_project(db, org, owner)
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, owner, role)
    db.commit()

    outsider = make_user(db, email="outsider_b@test.demo", nombre="Outsider B")
    db.commit()
    headers = auth_headers(outsider)

    res = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "feature", "title": "Hack", "status": "pendiente"},
        headers=headers,
    )
    assert res.status_code == 403


def test_member_can_access(client: TestClient, db):
    owner = make_user(db, email="owner_c@test.demo", nombre="Owner C")
    org = make_org(db, owner)
    project = make_project(db, org, owner)
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, owner, role)
    db.commit()

    headers = auth_headers(owner)
    res = client.get(f"/api/v1/projects/{project.id}/records", headers=headers)
    assert res.status_code == 200


def test_non_member_cannot_access_hub(client: TestClient, db):
    owner = make_user(db, email="owner_d@test.demo", nombre="Owner D")
    org = make_org(db, owner)
    project = make_project(db, org, owner)
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, owner, role)
    db.commit()

    outsider = make_user(db, email="outsider_c@test.demo", nombre="Outsider C")
    db.commit()
    headers = auth_headers(outsider)

    res = client.get(f"/api/v1/projects/{project.id}/hub", headers=headers)
    assert res.status_code == 403


def test_non_member_cannot_access_sprints(client: TestClient, db):
    owner = make_user(db, email="owner_e@test.demo", nombre="Owner E")
    org = make_org(db, owner)
    project = make_project(db, org, owner)
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, owner, role)
    db.commit()

    outsider = make_user(db, email="outsider_d@test.demo", nombre="Outsider D")
    db.commit()
    headers = auth_headers(outsider)

    res = client.get(f"/api/v1/projects/{project.id}/sprints", headers=headers)
    assert res.status_code == 403
