"""Tests devolver con hijos — modal G (F8)."""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_devolver_ch@test.demo", nombre="PM Devolver Ch")
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


def _story_in_sprint(client, project_id, headers, epic_id, sprint_id):
    story = client.post(
        f"/api/v1/projects/{project_id}/records",
        json={
            "record_type": "task",
            "title": "Story Devolver Ch",
            "parent_id": epic_id,
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project_id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint_id},
        headers=headers,
    )
    return story


def test_devolver_default_returns_active_dev_to_backlog(client: TestClient, db):
    """Sin children_on_return explícito → devs activos vuelven a backlog (bloque 3)."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint"},
        headers=headers,
    ).json()
    story = _story_in_sprint(client, project.id, headers, epic["id"], sprint["id"])
    dev = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev Active",
            "parent_id": story["id"],
            "status": "in_progress",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "devolver"},
        headers=headers,
    )
    assert res.status_code == 200, res.text

    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev['id']}",
        headers=headers,
    ).json()
    assert dev_after["status"] == "backlog"
    assert dev_after["parent_id"] == story["id"]


def test_devolver_return_to_backlog_moves_dev_and_subtask(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint"},
        headers=headers,
    ).json()
    story = _story_in_sprint(client, project.id, headers, epic["id"], sprint["id"])
    dev = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev Return",
            "parent_id": story["id"],
            "status": "to_do",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    sub = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Sub Return",
            "parent_id": dev["id"],
            "status": "in_review",
            "extra": {"scrum_role": "subtask"},
        },
        headers=headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "devolver", "children_on_return": "return_to_backlog"},
        headers=headers,
    )
    assert res.status_code == 200, res.text

    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev['id']}",
        headers=headers,
    ).json()
    sub_after = client.get(
        f"/api/v1/projects/{project.id}/records/{sub['id']}",
        headers=headers,
    ).json()
    assert dev_after["status"] == "backlog"
    assert sub_after["status"] == "backlog"


def test_devolver_return_to_backlog_keeps_inherited_blocked_dev(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint"},
        headers=headers,
    ).json()
    story = _story_in_sprint(client, project.id, headers, epic["id"], sprint["id"])
    dev = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev Inherited Block",
            "parent_id": story["id"],
            "status": "to_do",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        json={"title": "Bloqueo", "description": "Impedimento"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "devolver", "children_on_return": "return_to_backlog"},
        headers=headers,
    )
    assert res.status_code == 200, res.text

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev['id']}",
        headers=headers,
    ).json()
    assert story_after["status"] == "blocked"
    assert dev_after["status"] == "blocked"


def test_devolver_cancel_children_cancels_and_clears_blockers(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint"},
        headers=headers,
    ).json()
    story = _story_in_sprint(client, project.id, headers, epic["id"], sprint["id"])
    dev = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev Cancel",
            "parent_id": story["id"],
            "status": "in_progress",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/records/{dev['id']}/blockers",
        json={"title": "Bloqueo dev", "description": "Impedimento"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "devolver", "children_on_return": "cancel"},
        headers=headers,
    )
    assert res.status_code == 200, res.text

    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev['id']}",
        headers=headers,
    ).json()
    assert dev_after["status"] == "cancelled"

    blockers = client.get(
        f"/api/v1/projects/{project.id}/records/{dev['id']}/blockers",
        headers=headers,
    ).json()
    assert blockers == []
