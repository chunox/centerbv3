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


def _advance_epic_to_in_review(client, project_id, epic_id, headers, sprint_id: str | None = None):
    if sprint_id:
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

    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Cascade"},
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

    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Cascade"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    _advance_epic_to_in_review(client, project.id, epic["id"], headers, sprint["id"])

    client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "complete", "cascade": "all"},
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


def test_cascade_parent_only_blocked_when_stories_misaligned(client: TestClient, db):
    """Épica→done con cascade none falla si las historias no están alineadas."""
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

    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Cascade"},
        headers=headers,
    ).json()

    _advance_epic_to_in_review(client, project.id, epic["id"], headers, sprint["id"])
    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "complete", "cascade": "none"},
        headers=headers,
    )
    assert res.status_code == 422

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert epic_after["status"] == "in_review"
    assert story_after["status"] == "in_review"


def test_cascade_multihop_child_to_done(client: TestClient, db):
    """Hijo en to_do cuando padre completa — cascada aplica varios hops."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Multi", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Multi",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Multi"},
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
    _advance_epic_to_in_review(client, project.id, epic["id"], headers, sprint["id"])

    client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "complete", "cascade": "all"},
        headers=headers,
    )

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_after["status"] == "done"


def test_parent_transition_blocked_with_blocked_descendant(client: TestClient, db):
    """Épica no puede avanzar si una historia descendiente está en status=blocked."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Blocked Child", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Blocked",
            "parent_id": epic["id"],
            "status": "in_review",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()

    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Blocked"},
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
        json={"title": "Impedimento", "description": "Bloqueo de prueba"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "complete"},
        headers=headers,
    )
    assert res.status_code == 422
    assert "descendientes" in res.json()["detail"].lower() or "bloqueado" in res.json()["detail"].lower()


def test_cascade_all_fails_with_blocked_child(client: TestClient, db):
    """Cascada all falla si un hijo está bloqueado."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Cascade Blocked", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Cascade Blocked",
            "parent_id": epic["id"],
            "status": "in_review",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()

    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Cascade Blocked"},
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
        json={"title": "Impedimento cascada", "description": "Bloqueo"},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "complete", "cascade": "all"},
        headers=headers,
    )
    assert res.status_code == 422

    epic_after = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    ).json()
    assert epic_after["status"] == "in_review"


def test_skip_blocked_deprecated_returns_422(client: TestClient, db):
    """skip_blocked=true rechazado en validación del body."""
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Skip Blocked", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "start", "skip_blocked": True},
        headers=headers,
    )
    assert res.status_code == 422
    body = res.json()
    detail = body.get("detail", body)
    if isinstance(detail, list):
        detail = str(detail)
    assert "skip_blocked" in str(detail).lower()


def test_cascade_preview_marks_blocked_child(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Preview Blocked", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Preview Blocked",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()

    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Preview Blocked"},
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
        json={"title": "Impedimento preview", "description": "Bloqueo"},
        headers=headers,
    )

    preview = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition/preview",
        json={"action_id": "complete"},
        headers=headers,
    ).json()

    story_plan = next(c for c in preview["children"] if c["id"] == story["id"])
    assert story_plan["can_transition"] is False
    assert story_plan["reason"] == "blocked"
