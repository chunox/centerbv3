"""Tests desasignar épica del sprint — modal H (F9)."""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_epic_unassign@test.demo", nombre="PM Epic Unassign")
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


def _epic_in_sprint(client, project_id, headers, sprint_id):
    epic = client.post(
        f"/api/v1/projects/{project_id}/records",
        json={"record_type": "task", "title": "Epic Unassign", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project_id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint_id},
        headers=headers,
    )
    return epic


def test_unassign_epic_without_stories_succeeds(client: TestClient, db):
    project, headers = _scrum_pm(db)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Solo Epic"},
        headers=headers,
    ).json()
    epic = _epic_in_sprint(client, project.id, headers, sprint["id"])

    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": None},
        headers=headers,
    )
    assert res.status_code == 204

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    assert epic_after["status"] == "backlog"
    assert "sprint_id" not in (epic_after.get("extra") or {})


def test_unassign_epic_with_stories_requires_confirmation(client: TestClient, db):
    project, headers = _scrum_pm(db)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Confirm"},
        headers=headers,
    ).json()
    epic = _epic_in_sprint(client, project.id, headers, sprint["id"])
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story In Sprint",
            "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": None},
        headers=headers,
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["code"] == "requires_unassign_confirmation"
    assert len(detail["stories"]) == 1
    assert detail["stories"][0]["id"] == story["id"]

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    assert epic_after["extra"].get("sprint_id") == sprint["id"]


def test_unassign_preview_lists_affected_stories(client: TestClient, db):
    project, headers = _scrum_pm(db)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Preview"},
        headers=headers,
    ).json()
    epic = _epic_in_sprint(client, project.id, headers, sprint["id"])
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Preview",
            "parent_id": epic["id"],
            "status": "in_progress",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    dev = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev Preview",
            "parent_id": story["id"],
            "status": "to_do",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    preview = client.post(
        f"/api/v1/projects/{project.id}/sprints/unassign-epics/preview",
        json={"epic_ids": [epic["id"]]},
        headers=headers,
    ).json()

    assert preview["requires_confirmation"] is True
    assert len(preview["stories"]) == 1
    assert preview["stories"][0]["id"] == story["id"]
    child_ids = {c["id"] for c in preview["stories"][0]["children"]}
    assert dev["id"] in child_ids


def test_unassign_return_stories_and_children_to_backlog(client: TestClient, db):
    project, headers = _scrum_pm(db)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Return"},
        headers=headers,
    ).json()
    epic = _epic_in_sprint(client, project.id, headers, sprint["id"])
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Return",
            "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    dev = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev Return",
            "parent_id": story["id"],
            "status": "in_progress",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={
            "epic_ids": [epic["id"]],
            "sprint_id": None,
            "on_unassign_stories": "return",
            "on_unassign_children": "return_to_backlog",
        },
        headers=headers,
    )
    assert res.status_code == 204

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev['id']}",
        headers=headers,
    ).json()
    assert epic_after["status"] == "backlog"
    assert story_after["parent_id"] == epic["id"]
    assert story_after["status"] == "backlog"
    assert dev_after["status"] == "backlog"
    assert dev_after["parent_id"] == story["id"]


def test_unassign_cancel_stories_clears_blockers(client: TestClient, db):
    project, headers = _scrum_pm(db)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Cancel"},
        headers=headers,
    ).json()
    epic = _epic_in_sprint(client, project.id, headers, sprint["id"])
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Cancel",
            "parent_id": epic["id"],
            "status": "in_progress",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        json={"title": "Bloqueo", "description": "Impedimento"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={
            "epic_ids": [epic["id"]],
            "sprint_id": None,
            "on_unassign_stories": "cancel",
            "on_unassign_children": "unchanged",
        },
        headers=headers,
    )
    assert res.status_code == 204

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_after["status"] == "cancelled"
    assert story_after["parent_id"] == epic["id"]

    blockers = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        headers=headers,
    ).json()
    assert blockers == []


def test_unassign_abort_if_pending_leaves_all_unchanged(client: TestClient, db):
    project, headers = _scrum_pm(db)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Abort"},
        headers=headers,
    ).json()
    epic = _epic_in_sprint(client, project.id, headers, sprint["id"])
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Abort",
            "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={
            "epic_ids": [epic["id"]],
            "sprint_id": None,
            "on_unassign_stories": "abort_if_pending",
        },
        headers=headers,
    )
    assert res.status_code == 204

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert epic_after["extra"].get("sprint_id") == sprint["id"]
    assert story_after["parent_id"] == sprint["id"]


def test_unassign_blocked_epic_keeps_blocked_status(client: TestClient, db):
    project, headers = _scrum_pm(db)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Blocked Epic"},
        headers=headers,
    ).json()
    epic = _epic_in_sprint(client, project.id, headers, sprint["id"])
    client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/blockers",
        json={"title": "Bloqueo épica", "description": "Impedimento"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": None},
        headers=headers,
    )
    assert res.status_code == 204

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    assert epic_after["status"] == "blocked"
    assert "sprint_id" not in (epic_after.get("extra") or {})
