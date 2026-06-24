"""
Tests de ceremonias — crear sesiones, agregar entries, SSE smoke test.
"""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _setup(db, *, pack_slug="software-scrum", template_slug="t6_scrum_interno", delivery_mode="scrum"):
    user = make_user(db, email="pm_cer@test.demo", nombre="PM Ceremonies")
    org = make_org(db, user)
    project = make_project(db, org, user, pack_slug=pack_slug, template_slug=template_slug, delivery_mode=delivery_mode)
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, user, role)
    db.commit()
    return project, auth_headers(user), user


def test_list_ceremony_sessions_empty(client: TestClient, db):
    project, headers, _ = _setup(db)
    res = client.get(f"/api/v1/projects/{project.id}/ceremonies", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_planning_session(client: TestClient, db):
    project, headers, _ = _setup(db)
    res = client.post(
        f"/api/v1/projects/{project.id}/ceremonies",
        json={"session_type": "planning", "sprint_id": None},
        headers=headers,
    )
    assert res.status_code == 201
    session = res.json()
    assert session["session_type"] == "planning"
    assert session["status"] == "pendiente"


def test_create_daily_session(client: TestClient, db):
    project, headers, _ = _setup(db)
    res = client.post(
        f"/api/v1/projects/{project.id}/ceremonies",
        json={"session_type": "daily"},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json()["session_type"] == "daily"


def test_create_retro_session(client: TestClient, db):
    project, headers, _ = _setup(db)
    res = client.post(
        f"/api/v1/projects/{project.id}/ceremonies",
        json={"session_type": "retro"},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json()["session_type"] == "retro"


def test_list_entries_empty(client: TestClient, db):
    project, headers, _ = _setup(db)
    sess = client.post(
        f"/api/v1/projects/{project.id}/ceremonies",
        json={"session_type": "daily"},
        headers=headers,
    ).json()
    res = client.get(
        f"/api/v1/projects/{project.id}/ceremonies/{sess['id']}/entries",
        headers=headers,
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_add_entry_to_session(client: TestClient, db):
    project, headers, _ = _setup(db)
    sess = client.post(
        f"/api/v1/projects/{project.id}/ceremonies",
        json={"session_type": "daily"},
        headers=headers,
    ).json()
    res = client.post(
        f"/api/v1/projects/{project.id}/ceremonies/{sess['id']}/entries",
        json={"entry_type": "standup", "payload": {"did": "Trabajé en X", "will": "Continúo con X", "blockers": "Ninguno"}},
        headers=headers,
    )
    assert res.status_code == 201
    entry = res.json()
    assert entry["entry_type"] == "standup"


def test_close_ceremony_session(client: TestClient, db):
    project, headers, _ = _setup(db)
    sess = client.post(
        f"/api/v1/projects/{project.id}/ceremonies",
        json={"session_type": "retro"},
        headers=headers,
    ).json()
    res = client.post(
        f"/api/v1/projects/{project.id}/ceremonies/{sess['id']}/close",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "cerrada"


def test_non_member_cannot_access_ceremonies(client: TestClient, db):
    project, headers, _ = _setup(db)
    sess = client.post(
        f"/api/v1/projects/{project.id}/ceremonies",
        json={"session_type": "daily"},
        headers=headers,
    ).json()
    outsider = make_user(db, email="outsider_cer@test.demo", nombre="Outsider Cer")
    db.commit()
    outsider_headers = auth_headers(outsider)

    assert client.get(f"/api/v1/projects/{project.id}/ceremonies", headers=outsider_headers).status_code == 403
    assert client.get(
        f"/api/v1/projects/{project.id}/ceremonies/{sess['id']}",
        headers=outsider_headers,
    ).status_code == 403
    assert client.post(
        f"/api/v1/projects/{project.id}/ceremonies/{sess['id']}/start",
        headers=outsider_headers,
    ).status_code == 403
    assert client.get(
        f"/api/v1/projects/{project.id}/ceremonies/{sess['id']}/entries",
        headers=outsider_headers,
    ).status_code == 403
    assert client.post(
        f"/api/v1/projects/{project.id}/ceremonies/{sess['id']}/entries",
        json={"entry_type": "standup", "payload": {"did": "x"}},
        headers=outsider_headers,
    ).status_code == 403
