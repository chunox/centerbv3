"""Tests F12 — preview enriquecido y cascade_mode."""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_preview@test.demo", nombre="PM Preview")
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


def _assign_story_to_sprint(client, project_id, story_id, headers):
    sprint = client.post(
        f"/api/v1/projects/{project_id}/sprints",
        json={"title": "Sprint Preview"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project_id}/sprints/assign-stories",
        json={"story_ids": [story_id], "sprint_id": sprint["id"]},
        headers=headers,
    )
    return sprint


def test_preview_children_ahead_warning(client: TestClient, db):
    """Hijo más adelantado que el destino del padre → children_ahead + confirmación."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Epic Ahead",
            "status": "to_do",
            "extra": {"scrum_role": "epic"},
        },
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Ahead",
            "parent_id": epic["id"],
            "status": "in_review",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = _assign_story_to_sprint(client, project.id, story["id"], headers)
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    preview = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "start"},
        headers=headers,
    ).json()

    assert preview["to_status"] == "in_progress"
    assert preview["requires_confirmation"] is True
    ahead_ids = {c["id"] for c in preview["children_ahead"]}
    assert story["id"] in ahead_ids
    assert preview["children_ahead"][0]["from_status"] == "in_review"


def test_preview_blocked_in_chain_disables_modes(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Block Preview", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Block Preview",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = _assign_story_to_sprint(client, project.id, story["id"], headers)
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
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
        json={"title": "Block", "description": "Impedimento"},
        headers=headers,
    )

    preview = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "complete"},
        headers=headers,
    ).json()

    assert preview["blocked_in_chain"] is True
    assert preview["epic_done_blocked"] is True
    assert preview["cascade_modes_available"] == []


def test_preview_epic_done_misaligned_modes(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Misaligned", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Misaligned",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = _assign_story_to_sprint(client, project.id, story["id"], headers)
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    for action_id in ("start", "review"):
        client.post(
            f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
            json={"action_id": action_id},
            headers=headers,
        )

    preview = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "complete"},
        headers=headers,
    ).json()

    assert preview["epic_done_misaligned"] is True
    assert preview["blocked_in_chain"] is False
    assert preview["cascade_modes_available"] == ["all", "cancel_misaligned_stories"]


def test_apply_cancel_misaligned_stories_epic_done(client: TestClient, db):
    """cancel_misaligned_stories cancela historias abiertas aunque puedan moverse a done."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Cancel Misaligned", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story_done = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Done CM",
            "parent_id": epic["id"],
            "status": "done",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    story_open = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Open CM",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    dev_open = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev Open CM",
            "parent_id": story_open["id"],
            "status": "in_progress",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    sprint = _assign_story_to_sprint(client, project.id, story_open["id"], headers)
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story_done["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    for action_id in ("start", "review"):
        client.post(
            f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
            json={"action_id": action_id},
            headers=headers,
        )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "complete", "cascade_mode": "cancel_misaligned_stories"},
        headers=headers,
    )
    assert res.status_code == 200

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    open_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story_open['id']}",
        headers=headers,
    ).json()
    done_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story_done['id']}",
        headers=headers,
    ).json()
    dev_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev_open['id']}",
        headers=headers,
    ).json()

    assert epic_after["status"] == "done"
    assert open_after["status"] == "cancelled"
    assert done_after["status"] == "done"
    assert dev_after["status"] == "cancelled"


def test_apply_movable_and_cancel_rest_deps(client: TestClient, db):
    """movable_and_cancel_rest (modal deps) cancela hijos que no pueden alcanzar done."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Cancel Rest", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Cascade",
            "parent_id": epic["id"],
            "status": "in_review",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    dev_a = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev A",
            "parent_id": story["id"],
            "status": "in_review",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    dev_b = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev B",
            "parent_id": story["id"],
            "status": "to_do",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    sprint = _assign_story_to_sprint(client, project.id, story["id"], headers)
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/dependencies",
        json={"predecessor_id": dev_a["id"], "successor_id": dev_b["id"]},
        headers=headers,
    )
    for action_id in ("start", "review"):
        client.post(
            f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
            json={"action_id": action_id},
            headers=headers,
        )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "complete", "cascade_mode": "movable_and_cancel_rest"},
        headers=headers,
    )
    assert res.status_code == 200

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    dev_a_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev_a['id']}",
        headers=headers,
    ).json()
    dev_b_after = client.get(
        f"/api/v1/projects/{project.id}/records/{dev_b['id']}",
        headers=headers,
    ).json()

    assert epic_after["status"] == "done"
    assert dev_a_after["status"] == "done"
    assert dev_b_after["status"] == "cancelled"


def test_preview_dependency_offers_partial_modes(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Epic Dep",
            "status": "to_do",
            "extra": {"scrum_role": "epic"},
        },
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Dep",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    dev_a = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev A Dep",
            "parent_id": story["id"],
            "status": "to_do",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    dev_b = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Dev B Dep",
            "parent_id": story["id"],
            "status": "to_do",
            "extra": {"scrum_role": "dev"},
        },
        headers=headers,
    ).json()
    sprint = _assign_story_to_sprint(client, project.id, story["id"], headers)
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/dependencies",
        json={"predecessor_id": dev_a["id"], "successor_id": dev_b["id"]},
        headers=headers,
    )

    preview = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "start"},
        headers=headers,
    ).json()

    dev_b_plan = next(c for c in preview["children"] if c["id"] == dev_b["id"])
    assert dev_b_plan["reason"] == "dependency_unsatisfied"
    assert preview["epic_done_misaligned"] is False
    assert "movable_only" in preview["cascade_modes_available"]
    assert "movable_and_cancel_rest" in preview["cascade_modes_available"]
    assert "none" not in preview["cascade_modes_available"]


def test_preview_backlog_story_needs_sprint(client: TestClient, db):
    """Historia en product backlog bajo épica en sprint → needs_sprint en preview."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Epic Backlog Child",
            "status": "to_do",
            "extra": {"scrum_role": "epic"},
        },
        headers=headers,
    ).json()
    story_backlog = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story In Backlog",
            "parent_id": epic["id"],
            "status": "backlog",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    story_sprint = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story In Sprint",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = _assign_story_to_sprint(client, project.id, story_sprint["id"], headers)
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    preview = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "start"},
        headers=headers,
    ).json()

    backlog_plan = next(c for c in preview["children"] if c["id"] == story_backlog["id"])
    assert backlog_plan["reason"] == "needs_sprint"
    assert backlog_plan["can_transition"] is False
    assert "none" not in preview["cascade_modes_available"]


def test_preview_aligned_children_no_none_mode(client: TestClient, db):
    """Hijos alineados y movibles → solo cascade_mode all disponible."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Epic Aligned",
            "status": "to_do",
            "extra": {"scrum_role": "epic"},
        },
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Aligned",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = _assign_story_to_sprint(client, project.id, story["id"], headers)
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    preview = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "start"},
        headers=headers,
    ).json()

    assert preview["cascade_modes_available"] == ["all"]
