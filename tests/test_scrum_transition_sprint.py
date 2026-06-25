"""Tests de transiciones Scrum con asignación de sprint vía API."""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_trans_sprint@test.demo", nombre="PM Trans Sprint")
    org = make_org(db, user)
    project = make_project(
        db, org, user,
        pack_slug="software-scrum",
        template_slug="t6_scrum_interno",
        delivery_mode="scrum",
    )
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, user, role)
    db.commit()
    return project, auth_headers(user)


def test_preview_story_backlog_to_todo_flags_requires_sprint(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "move_to_todo"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["requires_sprint_assignment"] is True
    assert data["to_status"] == "to_do"


def test_transition_with_sprint_id_assigns_and_moves(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Atomic"},
        headers=headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "move_to_todo", "sprint_id": sprint["id"]},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "to_do"
    assert data["extra"]["sprint_id"] == sprint["id"]


def test_transition_without_sprint_returns_structured_422(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "move_to_todo"},
        headers=headers,
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["code"] == "requires_sprint_assignment"
    assert detail["record_id"] == epic["id"]


def test_assign_epics_happy_path(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Assign", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Epic"},
        headers=headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    assert res.status_code == 204

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    assert epic_after["extra"]["sprint_id"] == sprint["id"]
    assert epic_after["status"] == "to_do"


def test_no_active_sprint_returns_null_active_sprint_id(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition/preview",
        json={"action_id": "iniciar"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["requires_sprint_assignment"] is True
    assert data["active_sprint_id"] is None
