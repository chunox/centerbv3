"""Tests de workflows Scrum unificados (7 estados)."""
from fastapi.testclient import TestClient

from app.domain.packs.definitions import SCRUM_PACK
from app.domain.scrum.states import SCRUM_KANBAN_STATES
from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_workflows@test.demo", nombre="PM Workflows")
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


def test_epic_workflow_has_seven_states():
    epic_wf = SCRUM_PACK.workflows["epic"]
    assert epic_wf.states == SCRUM_KANBAN_STATES
    assert "blocked" in epic_wf.states


def test_story_devolver_allows_blocked_state():
    story_wf = SCRUM_PACK.workflows["story"]
    devolver = next(t for t in story_wf.transitions if t.action_id == "devolver")
    assert "blocked" in devolver.from_states


def test_subtask_workflow_has_in_review():
    sub_wf = SCRUM_PACK.workflows["subtask"]
    assert "in_review" in sub_wf.states


def test_epic_full_pipeline_transitions(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Pipeline", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Pipeline"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    assert epic["status"] == "backlog"

    for action_id, expected in (
        ("start", "in_progress"),
        ("review", "in_review"),
        ("complete", "done"),
    ):
        res = client.post(
            f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
            json={"action_id": action_id},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == expected


def test_subtask_pipeline_includes_review(client: TestClient, db):
    project, headers = _scrum_pm(db)

    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Sub",
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sub = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Subtask Review",
            "parent_id": story["id"],
            "extra": {"scrum_role": "subtask"},
        },
        headers=headers,
    ).json()

    for action_id, expected in (
        ("move_to_todo", "to_do"),
        ("start", "in_progress"),
        ("review", "in_review"),
        ("complete", "done"),
    ):
        res = client.post(
            f"/api/v1/projects/{project.id}/records/{sub['id']}/transition",
            json={"action_id": action_id},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == expected


def test_story_start_without_sprint_returns_422(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Gate", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story No Sprint",
            "parent_id": epic["id"],
            "status": "to_do",
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "iniciar"},
        headers=headers,
    )
    assert res.status_code == 422


def test_epic_move_to_todo_without_sprint_returns_422(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Gate", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{epic['id']}/transition",
        json={"action_id": "move_to_todo"},
        headers=headers,
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    if isinstance(detail, dict):
        assert detail.get("code") == "requires_sprint_assignment"


def test_story_in_sprint_can_start(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Sprint", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Sprint",
            "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Gate"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "iniciar"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "in_progress"
