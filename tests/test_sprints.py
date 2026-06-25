"""
Tests de sprints — crear, activar, cerrar, asignar historias.
"""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _setup_project(db):
    user = make_user(db, email="pm_s@test.demo", nombre="PM Sprints")
    org = make_org(db, user)
    project = make_project(db, org, user, pack_slug="software-scrum", template_slug="t6_scrum_interno", delivery_mode="scrum")
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, user, role)
    db.commit()
    return project, auth_headers(user)


def test_create_sprint(client: TestClient, db):
    project, headers = _setup_project(db)
    res = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint 1", "goal": "Completar login"},
        headers=headers,
    )
    assert res.status_code == 201
    sprint = res.json()
    assert sprint["title"] == "Sprint 1"
    assert sprint["goal"] == "Completar login"
    assert sprint["status"] == "pendiente"


def test_list_sprints_empty(client: TestClient, db):
    project, headers = _setup_project(db)
    res = client.get(f"/api/v1/projects/{project.id}/sprints", headers=headers)
    assert res.status_code == 200
    assert res.json() == []


def test_activate_sprint(client: TestClient, db):
    project, headers = _setup_project(db)
    create_res = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint A"},
        headers=headers,
    )
    sprint_id = create_res.json()["id"]
    res = client.post(f"/api/v1/projects/{project.id}/sprints/{sprint_id}/activate", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "activo"
    assert res.json()["is_active"] is True


def test_activate_sprint_already_active(client: TestClient, db):
    project, headers = _setup_project(db)
    sprint_res = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint B"},
        headers=headers,
    )
    sprint_id = sprint_res.json()["id"]
    client.post(f"/api/v1/projects/{project.id}/sprints/{sprint_id}/activate", headers=headers)
    res = client.post(f"/api/v1/projects/{project.id}/sprints/{sprint_id}/activate", headers=headers)
    assert res.status_code == 409


def test_get_active_sprint_none(client: TestClient, db):
    project, headers = _setup_project(db)
    res = client.get(f"/api/v1/projects/{project.id}/sprints/active", headers=headers)
    assert res.status_code == 200
    assert res.json() is None


def test_update_sprint(client: TestClient, db):
    project, headers = _setup_project(db)
    sprint_res = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint C"},
        headers=headers,
    )
    sprint_id = sprint_res.json()["id"]
    res = client.patch(
        f"/api/v1/projects/{project.id}/sprints/{sprint_id}",
        json={"title": "Sprint C editado", "goal": "Nuevo objetivo"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Sprint C editado"
    assert data["goal"] == "Nuevo objetivo"


def test_close_sprint(client: TestClient, db):
    project, headers = _setup_project(db)
    sprint_res = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint D"},
        headers=headers,
    )
    sprint_id = sprint_res.json()["id"]
    client.post(f"/api/v1/projects/{project.id}/sprints/{sprint_id}/activate", headers=headers)
    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/{sprint_id}/close",
        json={"incomplete_action": "backlog", "resolutions": []},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "cerrado"


def _setup_with_dev(db):
    pm = make_user(db, email="pm_s2@test.demo", nombre="PM Sprints 2")
    dev = make_user(db, email="dev_s@test.demo", nombre="Dev Sprints")
    org = make_org(db, pm)
    project = make_project(
        db, org, pm,
        pack_slug="software-scrum",
        template_slug="t6_scrum_interno",
        delivery_mode="scrum",
    )
    pm_role = make_project_role(db, project, slug="pm")
    dev_role = make_project_role(db, project, slug="dev", nombre="Dev")
    make_member(db, project, pm, pm_role)
    make_member(db, project, dev, dev_role)
    db.commit()
    return project, auth_headers(pm), auth_headers(dev)


def _create_epic_story(client, project, headers):
    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task", "title": "Story", "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    return epic, story


def test_assign_stories_happy_path(client: TestClient, db):
    project, pm_headers, _ = _setup_with_dev(db)
    epic, story = _create_epic_story(client, project, pm_headers)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Assign"},
        headers=pm_headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=pm_headers,
    )
    assert res.status_code == 204

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=pm_headers,
    ).json()
    assert story_after["parent_id"] == sprint["id"]
    assert story_after["extra"].get("original_parent_id") == epic["id"]


def test_unassign_stories_clears_sprint_link(client: TestClient, db):
    project, pm_headers, _ = _setup_with_dev(db)
    epic, story = _create_epic_story(client, project, pm_headers)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Unassign"},
        headers=pm_headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=pm_headers,
    )
    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": None},
        headers=pm_headers,
    )
    assert res.status_code == 204
    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=pm_headers,
    ).json()
    assert story_after["parent_id"] == epic["id"]
    assert story_after["status"] == "backlog"
    assert "original_parent_id" not in story_after["extra"]


def test_dev_forbidden_assign_stories(client: TestClient, db):
    project, pm_headers, dev_headers = _setup_with_dev(db)
    _, story = _create_epic_story(client, project, pm_headers)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Dev Block"},
        headers=pm_headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=dev_headers,
    )
    assert res.status_code == 403


def test_close_sprint_moves_incomplete_stories_to_backlog(client: TestClient, db):
    project, pm_headers, _ = _setup_with_dev(db)
    epic, story = _create_epic_story(client, project, pm_headers)
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Close"},
        headers=pm_headers,
    ).json()
    client.post(f"/api/v1/projects/{project.id}/sprints/{sprint['id']}/activate", headers=pm_headers)
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint["id"]},
        headers=pm_headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/sprints/{sprint['id']}/close",
        json={"incomplete_action": "backlog"},
        headers=pm_headers,
    )
    assert res.status_code == 200

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=pm_headers,
    ).json()
    assert story_after["parent_id"] == epic["id"]
    assert story_after["status"] == "backlog"
    assert "original_parent_id" not in story_after["extra"]


def test_activate_closes_previous_sprint(client: TestClient, db):
    project, pm_headers, _ = _setup_with_dev(db)
    epic, story = _create_epic_story(client, project, pm_headers)

    sprint1 = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Prev"},
        headers=pm_headers,
    ).json()
    client.post(f"/api/v1/projects/{project.id}/sprints/{sprint1['id']}/activate", headers=pm_headers)
    client.post(
        f"/api/v1/projects/{project.id}/sprints/assign-stories",
        json={"story_ids": [story["id"]], "sprint_id": sprint1["id"]},
        headers=pm_headers,
    )

    sprint2 = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Next"},
        headers=pm_headers,
    ).json()
    client.post(f"/api/v1/projects/{project.id}/sprints/{sprint2['id']}/activate", headers=pm_headers)

    sprint1_after = client.get(
        f"/api/v1/projects/{project.id}/sprints",
        headers=pm_headers,
    ).json()
    prev = next(s for s in sprint1_after if s["id"] == sprint1["id"])
    assert prev["status"] == "cerrado"

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=pm_headers,
    ).json()
    assert story_after["parent_id"] == epic["id"]
    assert story_after["status"] == "backlog"
    assert "original_parent_id" not in story_after["extra"]
