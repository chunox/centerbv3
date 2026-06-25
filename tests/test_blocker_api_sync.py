"""Tests HTTP — create/resolve blocker sincroniza status=blocked (F2)."""
from fastapi.testclient import TestClient

from app.domain.scrum.states import EXTRA_BLOCKED_BY_INHERITANCE, EXTRA_STATUS_BEFORE_BLOCK
from tests.conftest import make_member, make_org, make_project, make_project_role, make_user, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="block_api@test.demo", nombre="PM Block API")
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


def test_create_blocker_sets_status_and_cascades_scrum(client: TestClient, db):
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
            "status": "in_progress",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    dev = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev",
            "parent_id": story["id"],
            "status": "to_do",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()

    block_res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        json={"description": "impedimento"},
        headers=headers,
    )
    assert block_res.status_code == 201, block_res.text

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev['id']}",
        headers=headers,
    ).json()

    assert story_after["status"] == "blocked"
    assert story_after["extra"][EXTRA_STATUS_BEFORE_BLOCK] == "in_progress"
    assert dev_after["status"] == "blocked"
    assert dev_after["extra"].get(EXTRA_BLOCKED_BY_INHERITANCE) is True


def test_resolve_blocker_restores_status_scrum(client: TestClient, db):
    project, headers = _scrum_pm(db)

    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Restore",
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()

    blocker_res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        json={"description": "temp"},
        headers=headers,
    ).json()

    resolve_res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers/{blocker_res['id']}/resolve",
        json={"resolution_note": "ok"},
        headers=headers,
    )
    assert resolve_res.status_code == 200, resolve_res.text

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_after["status"] == "to_do"
    assert EXTRA_STATUS_BEFORE_BLOCK not in story_after.get("extra", {})


def test_block_done_child_unchanged_when_parent_blocked(client: TestClient, db):
    project, headers = _scrum_pm(db)

    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Done Child",
            "status": "in_progress",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    dev_done = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev Done",
            "parent_id": story["id"],
            "status": "done",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        json={"description": "block story"},
        headers=headers,
    )

    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev_done['id']}",
        headers=headers,
    ).json()
    assert dev_after["status"] == "done"
