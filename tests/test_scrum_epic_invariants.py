"""Tests del invariante épica done (F5)."""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_epic_inv@test.demo", nombre="PM Epic Inv")
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


def _advance_epic_to_in_review(client, project_id, epic_id, headers, sprint_id: str):
    client.post(
        f"/api/v1/projects/{project_id}/sprints/assign-epics",
        json={"epic_ids": [epic_id], "sprint_id": sprint_id},
        headers=headers,
    )
    for action_id in ("start", "review"):
        client.post(
            f"/api/v1/projects/{project_id}/records/{epic_id}/transition",
            json={"action_id": action_id},
            headers=headers,
        )


def test_epic_done_cascade_none_rejects_misaligned_stories(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Inv", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Inv",
            "parent_id": epic["id"],
            "status": "in_progress",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Inv"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    _advance_epic_to_in_review(client, project.id, epic["id"], headers, sprint["id"])

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "complete", "cascade": "none"},
        headers=headers,
    )
    assert res.status_code == 422
    assert "historia" in res.json()["detail"].lower()


def test_epic_done_allowed_when_all_stories_terminal(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Aligned", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story_done = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Done",
            "parent_id": epic["id"],
            "status": "done",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    story_cancelled = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Cancelled",
            "parent_id": epic["id"],
            "status": "cancelled",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Aligned"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story_done["id"], story_cancelled["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    _advance_epic_to_in_review(client, project.id, epic["id"], headers, sprint["id"])

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "complete", "cascade": "none"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "done"


def test_epic_done_preview_shows_misaligned_stories(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Preview Inv", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Preview Inv",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Preview Inv"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    _advance_epic_to_in_review(client, project.id, epic["id"], headers, sprint["id"])

    preview = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "complete"},
        headers=headers,
    ).json()

    assert preview["requires_confirmation"] is True
    assert preview["epic_done_blocked"] is False
    assert len(preview["stories_misaligned"]) == 1
    assert preview["stories_misaligned"][0]["id"] == story["id"]
    assert preview["stories_misaligned"][0]["status"] == "to_do"


def test_epic_done_preview_blocked_when_descendant_blocked(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Blocked Preview", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Blocked Preview",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Blocked Preview"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    _advance_epic_to_in_review(client, project.id, epic["id"], headers, sprint["id"])
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        json={"title": "Bloqueo", "description": "Impedimento"},
        headers=headers,
    )

    preview = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "complete"},
        headers=headers,
    ).json()

    assert preview["epic_done_blocked"] is True
    assert len(preview["stories_misaligned"]) >= 1
