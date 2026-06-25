"""Tests del endpoint GET /scrum/workspace."""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_pm(db):
    user = make_user(db, email="pm_workspace@test.demo", nombre="PM Workspace")
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


def test_workspace_includes_backlog_stories(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic WS", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Backlog",
            "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()

    res = client.get(f"/api/v1/projects/{project.id}/scrum/workspace", headers=headers)
    assert res.status_code == 200
    data = res.json()
    story_ids = {s["id"] for s in data["stories"]}
    assert story["id"] in story_ids
    backlog = next(s for s in data["stories"] if s["id"] == story["id"])
    assert backlog["status"] == "backlog"
    assert backlog["in_product_backlog"] is True


def test_workspace_includes_sprint_stories(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic WS", "extra": {"scrum_role": "epic"}},
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
        json={"title": "Sprint WS"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    res = client.get(
        f"/api/v1/projects/{project.id}/scrum/workspace?sprint_id={sprint['id']}",
        headers=headers,
    )
    assert res.status_code == 200
    story_ids = {s["id"] for s in res.json()["stories"]}
    assert story["id"] in story_ids


def test_workspace_epic_visible_via_sprint_id(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Sprint ID", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Epic"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    res = client.get(
        f"/api/v1/projects/{project.id}/scrum/workspace?sprint_id={sprint['id']}",
        headers=headers,
    )
    epic_ids = {e["id"] for e in res.json()["epics"]}
    assert epic["id"] in epic_ids


def test_workspace_epic_visible_via_child_story(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Child", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Child",
            "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Child"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    res = client.get(
        f"/api/v1/projects/{project.id}/scrum/workspace?sprint_id={sprint['id']}",
        headers=headers,
    )
    epic_ids = {e["id"] for e in res.json()["epics"]}
    assert epic["id"] in epic_ids


def test_record_response_sprint_id_derived(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Derived", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Derived"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-epics",
        json={"epic_ids": [epic["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    res = client.get(
        f"/api/v1/projects/{project.id}/records/{epic['id']}",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["sprint_id"] == sprint["id"]
    assert data["in_product_backlog"] is False


def test_workspace_includes_blocked_story_devuelta(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic WS Block", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Blocked PB",
            "parent_id": epic["id"],
            "status": "blocked",
            "extra": {"scrum_role": "story", "status_before_block": "in_progress"},
        },
        headers=headers,
    ).json()

    res = client.get(f"/api/v1/projects/{project.id}/scrum/workspace", headers=headers)
    assert res.status_code == 200
    data = res.json()
    story_ids = {s["id"] for s in data["stories"]}
    assert story["id"] in story_ids
    blocked = next(s for s in data["stories"] if s["id"] == story["id"])
    assert blocked["status"] == "blocked"
    assert blocked["in_product_backlog"] is True
    assert blocked["is_blocked"] is True


def test_workspace_sprint_excludes_backlog_stories(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Split", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    backlog_story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story PB Only",
            "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint_story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Sprint Only",
            "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Split"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [sprint_story["id"]], "sprint_id": sprint["id"]},
        headers=headers,
    )

    res = client.get(
        f"/api/v1/projects/{project.id}/scrum/workspace?sprint_id={sprint['id']}",
        headers=headers,
    )
    assert res.status_code == 200
    story_ids = {s["id"] for s in res.json()["stories"]}
    assert sprint_story["id"] in story_ids
    assert backlog_story["id"] not in story_ids


def test_list_records_filter_blocked(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Filter", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    blocked = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Blocked",
            "parent_id": epic["id"],
            "status": "blocked",
            "extra": {"scrum_role": "story", "status_before_block": "in_progress"},
        },
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Active",
            "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    )

    res = client.get(
        f"/api/v1/projects/{project.id}/records?status=blocked&record_type=task",
        headers=headers,
    )
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == blocked["id"]
    assert items[0]["status"] == "blocked"
