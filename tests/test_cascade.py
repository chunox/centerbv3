"""
Tests de transiciones en cascada (Scrum kanban).
"""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_cascade@test.demo", nombre="PM Cascade")
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


def test_cascade_preview_epic_with_mixed_children(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Cascade", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Cascade",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    dev = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev Cascade",
            "parent_id": story["id"],
            "status": "in_progress",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()

    # Epic in_progress -> done preview
    client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "iniciar"},
        headers=headers,
    )

    preview = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "completar"},
        headers=headers,
    ).json()

    assert preview["requires_confirmation"] is True
    assert preview["to_status"] == "done"
    child_ids = {c["id"] for c in preview["children"]}
    assert story["id"] in child_ids
    assert dev["id"] in child_ids


def test_cascade_apply_epic_moves_descendants(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Apply", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Apply",
            "parent_id": epic["id"],
            "status": "in_review",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    dev = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev Apply",
            "parent_id": story["id"],
            "status": "in_review",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "iniciar"},
        headers=headers,
    )

    client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "completar", "cascade": "all"},
        headers=headers,
    )

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev['id']}",
        headers=headers,
    ).json()
    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()

    assert epic_after["status"] == "done"
    assert story_after["status"] == "done"
    assert dev_after["status"] == "done"


def test_cascade_parent_only_leaves_children(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Solo", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Solo",
            "parent_id": epic["id"],
            "status": "in_review",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "iniciar"},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "completar", "cascade": "none"},
        headers=headers,
    )

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_after["status"] == "in_review"
