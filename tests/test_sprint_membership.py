"""Tests de sprint membership (historias y épicas)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord
from app.services.scrum.sprint_membership import (
    assert_scrum_invariants,
    assign_epic_to_sprint,
    assign_story_to_sprint,
    unassign_epic_from_sprint,
    unassign_story_from_sprint,
)
from app.services.workflow.errors import WorkflowError
from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_membership@test.demo", nombre="PM Membership")
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


def _create_epic_story(client, project, headers):
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
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    return epic, story


def test_assign_story_sets_parent_and_todo(client: TestClient, db):
    project, headers = _scrum_pm(db)
    epic, story = _create_epic_story(client, project, headers)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint M"},
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_after["parent_id"] == sprint["id"]
    assert story_after["status"] == "to_do"
    assert story_after["extra"].get("original_parent_id") == epic["id"]


def test_unassign_story_restores_epic_and_backlog(client: TestClient, db):
    project, headers = _scrum_pm(db)
    epic, story = _create_epic_story(client, project, headers)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint U"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": None},
        headers=headers,
    )

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_after["parent_id"] == epic["id"]
    assert story_after["status"] == "backlog"


def test_assign_epic_sets_sprint_id_and_todo(db: Session):
    project, headers = _scrum_pm(db)
    user = make_user(db, email="svc_epic@test.demo", nombre="SVC")
    epic = ProjectRecord(
        project_id=project.id,
        record_type="task",
        title="Epic SVC",
        status="backlog",
        extra={"scrum_role": "epic"},
        created_by=user.id,
    )
    sprint = ProjectRecord(
        project_id=project.id,
        record_type="sprint",
        title="Sprint SVC",
        status="pendiente",
        created_by=user.id,
    )
    db.add_all([epic, sprint])
    db.flush()

    assign_epic_to_sprint(db, epic, str(sprint.id))
    db.commit()
    db.refresh(epic)

    assert epic.extra.get("sprint_id") == str(sprint.id)
    assert epic.status == "to_do"


def test_unassign_epic_clears_sprint_and_backlog(db: Session):
    project, _ = _scrum_pm(db)
    user = make_user(db, email="svc_epic2@test.demo", nombre="SVC2")
    epic = ProjectRecord(
        project_id=project.id,
        record_type="task",
        title="Epic SVC2",
        status="to_do",
        extra={"scrum_role": "epic", "sprint_id": "fake"},
        created_by=user.id,
    )
    db.add(epic)
    db.flush()

    unassign_epic_from_sprint(db, epic)
    db.commit()
    db.refresh(epic)

    assert "sprint_id" not in (epic.extra or {})
    assert epic.status == "backlog"


def test_invariant_story_backlog_requires_epic_parent(db: Session):
    project, _ = _scrum_pm(db)
    user = make_user(db, email="inv@test.demo", nombre="Inv")
    sprint = ProjectRecord(
        project_id=project.id,
        record_type="sprint",
        title="S",
        status="activo",
        created_by=user.id,
    )
    story = ProjectRecord(
        project_id=project.id,
        record_type="task",
        title="Bad",
        status="backlog",
        parent_id=None,
        extra={"scrum_role": "story"},
        created_by=user.id,
    )
    db.add_all([sprint, story])
    db.flush()
    story.parent_id = sprint.id
    db.flush()

    with pytest.raises(WorkflowError):
        assert_scrum_invariants(db, story)


def test_invariant_epic_todo_requires_sprint_id(db: Session):
    project, _ = _scrum_pm(db)
    user = make_user(db, email="inv2@test.demo", nombre="Inv2")
    epic = ProjectRecord(
        project_id=project.id,
        record_type="task",
        title="Epic Bad",
        status="to_do",
        extra={"scrum_role": "epic"},
        created_by=user.id,
    )
    db.add(epic)
    db.flush()

    with pytest.raises(WorkflowError):
        assert_scrum_invariants(db, epic)


def test_unassign_epic_blocked_keeps_status(db: Session):
    project, _ = _scrum_pm(db)
    user = make_user(db, email="epic_blocked@test.demo", nombre="Epic Blocked")
    epic = ProjectRecord(
        project_id=project.id,
        record_type="task",
        title="Epic Blocked",
        status="blocked",
        extra={
            "scrum_role": "epic",
            "sprint_id": "sprint-fake",
            "status_before_block": "to_do",
        },
        created_by=user.id,
    )
    db.add(epic)
    db.flush()

    unassign_epic_from_sprint(db, epic)
    db.commit()
    db.refresh(epic)

    assert "sprint_id" not in (epic.extra or {})
    assert epic.status == "blocked"


def test_in_product_backlog_blocked_story_under_epic(db: Session):
    from app.services.scrum.sprint_membership import is_in_product_backlog

    project, _ = _scrum_pm(db)
    user = make_user(db, email="pb_blocked@test.demo", nombre="PB")
    epic = ProjectRecord(
        project_id=project.id,
        record_type="task",
        title="Epic PB",
        status="backlog",
        extra={"scrum_role": "epic"},
        created_by=user.id,
    )
    story = ProjectRecord(
        project_id=project.id,
        record_type="task",
        title="Story PB",
        status="blocked",
        parent_id=None,
        extra={"scrum_role": "story", "status_before_block": "in_progress"},
        created_by=user.id,
    )
    db.add(epic)
    db.flush()
    story.parent_id = epic.id
    db.add(story)
    db.flush()

    assert is_in_product_backlog(db, story) is True
