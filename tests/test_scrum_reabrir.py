"""Tests de transición reabrir (F6)."""
from fastapi.testclient import TestClient

from app.domain.packs.definitions import SCRUM_PACK
from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_reabrir@test.demo", nombre="PM Reabrir")
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


def _scrum_dev(db, project):
    user = make_user(db, email="dev_reabrir@test.demo", nombre="Dev Reabrir")
    role = make_project_role(db, project, slug="dev")
    make_member(db, project, user, role)
    db.commit()
    return auth_headers(user)


def _advance_epic_to_done(client, project_id, epic_id, headers, sprint_id: str):
    client.post(
        f"/api/v1/projects/{project_id}/sprints/assign-epics",
        json={"epic_ids": [epic_id], "sprint_id": sprint_id},
        headers=headers,
    )
    for action_id in ("start", "review", "complete"):
        client.post(
            f"/api/v1/projects/{project_id}/records/{epic_id}/transition",
            json={"action_id": action_id},
            headers=headers,
        )


def test_epic_workflow_has_reabrir_transitions():
    epic_wf = SCRUM_PACK.workflows["epic"]
    reabrir = [t for t in epic_wf.transitions if t.action_id == "reabrir"]
    assert len(reabrir) == 3
    from_states = {fs for t in reabrir for fs in t.from_states}
    assert from_states == {"done", "in_review", "in_progress"}


def test_reabrir_epic_done_preserves_sprint_id(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Reabrir", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Reabrir"},
        headers=headers,
    ).json()
    _advance_epic_to_done(client, project.id, epic["id"], headers, sprint["id"])

    epic_before = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    sprint_id_before = (epic_before.get("extra") or {}).get("sprint_id")
    assert epic_before["status"] == "done"
    assert sprint_id_before == sprint["id"]

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "reabrir"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    epic_after = res.json()
    assert epic_after["status"] == "in_review"
    assert (epic_after.get("extra") or {}).get("sprint_id") == sprint_id_before


def test_reabrir_fails_with_blocked_descendant(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Blocked Reabrir", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Blocked Reabrir",
            "parent_id": epic["id"],
            "status": "in_progress",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Blocked Reabrir"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    for action_id in ("start", "review"):
        client.post(
            f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
            json={"action_id": action_id},
            headers=headers,
        )
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        json={"title": "Bloqueo", "description": "Impedimento"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "reabrir"},
        headers=headers,
    )
    assert res.status_code == 422

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    assert epic_after["status"] == "in_review"


def test_reopen_children_moves_done_stories_to_in_review(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Reopen Kids", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story_done = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Done Kid",
            "parent_id": epic["id"],
            "status": "done",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    story_active = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Cancelled Kid",
            "parent_id": epic["id"],
            "status": "cancelled",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Reopen Kids"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story_done["id"], story_active["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    _advance_epic_to_done(client, project.id, epic["id"], headers, sprint["id"])

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "reabrir", "reopen_children": True},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "in_review"

    story_done_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story_done['id']}",
        headers=headers,
    ).json()
    story_active_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story_active['id']}",
        headers=headers,
    ).json()
    assert story_done_after["status"] == "in_review"
    assert story_active_after["status"] == "cancelled"


def test_dev_cannot_reabrir_epic(client: TestClient, db):
    project, pm_headers = _scrum_pm(db)
    dev_headers = _scrum_dev(db, project)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Dev Forbidden", "extra": {"scrum_role": "epic"}},
        headers=pm_headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Dev Forbidden"},
        headers=pm_headers,
    ).json()
    _advance_epic_to_done(client, project.id, epic["id"], pm_headers, sprint["id"])

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "reabrir"},
        headers=dev_headers,
    )
    assert res.status_code == 403


def test_reabrir_epic_cascade_moves_aligned_children_to_in_progress(client: TestClient, db):
    """Épica e hijos en in_review → reabrir con cascade all lleva a in_progress a toda la rama."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Cascade Reabrir", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Cascade Reabrir",
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
            "title": "Dev Cascade Reabrir",
            "parent_id": story["id"],
            "status": "in_review",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Cascade Reabrir"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    for action_id in ("start", "review"):
        client.post(
            f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
            json={"action_id": action_id},
            headers=headers,
        )

    epic_before = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    assert epic_before["status"] == "in_review"

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "reabrir", "cascade_mode": "all"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "in_progress"

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev['id']}",
        headers=headers,
    ).json()
    assert story_after["status"] == "in_progress"
    assert dev_after["status"] == "in_progress"
