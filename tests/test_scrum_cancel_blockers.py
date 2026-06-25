"""Tests cancel + eliminación de blockers (F7)."""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_cancel_blk@test.demo", nombre="PM Cancel Block")
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


def test_cancel_blocked_story_clears_blockers(client: TestClient, db):
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
            "title": "Story Blocked Cancel",
            "parent_id": epic["id"],
            "status": "in_progress",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        json={"title": "Impedimento", "description": "Bloqueo"},
        headers=headers,
    )
    story_blocked = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_blocked["status"] == "blocked"

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "cancelar"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"

    blockers = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        headers=headers,
    ).json()
    assert blockers == []

    blockers_resolved = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        params={"include_resolved": True},
        headers=headers,
    ).json()
    assert len(blockers_resolved) == 1
    assert blockers_resolved[0]["resolved_at"] is not None


def test_cancel_epic_with_children_cancels_descendants_and_clears_blockers(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Cancel Branch", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Branch",
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
            "title": "Dev Branch",
            "parent_id": story["id"],
            "status": "to_do",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        json={"title": "Bloqueo historia", "description": "Impedimento"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "cancel", "cancel_children": "all"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev['id']}",
        headers=headers,
    ).json()
    assert story_after["status"] == "cancelled"
    assert dev_after["status"] == "cancelled"

    story_blockers = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        headers=headers,
    ).json()
    assert story_blockers == []


def test_cancel_blocked_epic_succeeds(client: TestClient, db):
    """cancel es exento de regla global — épica blocked puede cancelarse."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Epic Self Blocked",
            "status": "in_progress",
            "extra": {"scrum_role": "epic"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/blockers",
        json={"title": "Bloqueo épica", "description": "Impedimento"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "cancel"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"
