"""
Tests de side effects de workflow — sync milestone/feature.
"""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _waterfall_pm(db):
    user = make_user(db, email="pm_sync@test.demo", nombre="PM Sync")
    org = make_org(db, user)
    project = make_project(db, org, user)
    role = make_project_role(db, project, slug="pm")
    make_member(db, project, user, role)
    db.commit()
    return project, auth_headers(user)


def test_complete_tasks_syncs_feature_and_milestone(client: TestClient, db):
    project, headers = _waterfall_pm(db)

    milestone = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "milestone", "title": "M1"},
        headers=headers,
    ).json()
    feature = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "feature", "title": "F1", "parent_id": milestone["id"]},
        headers=headers,
    ).json()
    task = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "T1", "parent_id": feature["id"]},
        headers=headers,
    ).json()

    for action in ("move_to_todo", "start", "review", "complete"):
        client.post(
            f"/api/v1/projects/{project.id}/records/{task['id']}/transition",
            json={"action_id": action},
            headers=headers,
        )

    feature_after = client.get(
        f"/api/v1/projects/{project.id}/records/{feature['id']}",
        headers=headers,
    ).json()
    milestone_after = client.get(
        f"/api/v1/projects/{project.id}/records/{milestone['id']}",
        headers=headers,
    ).json()

    assert feature_after["status"] == "done"
    assert milestone_after["status"] == "done"


def _scrum_pm(db):
    user = make_user(db, email="pm_scrum_se@test.demo", nombre="PM Scrum SE")
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


def test_comprometer_reparents_story_to_active_sprint(client: TestClient, db):
    project, headers = _scrum_pm(db)

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
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint 1"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/projects/{project.id}/sprints/{sprint['id']}/activate", headers=headers)

    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "comprometer"},
        headers=headers,
    )

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_after["parent_id"] == sprint["id"]
    assert story_after["extra"].get("original_parent_id") == epic["id"]


def test_devolver_reparents_story_to_epic(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic2", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task", "title": "Story2", "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint 2"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/projects/{project.id}/sprints/{sprint['id']}/activate", headers=headers)
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "comprometer"},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "devolver"},
        headers=headers,
    )

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_after["parent_id"] == epic["id"]
    assert story_after["status"] == "backlog"


def test_devolver_blocked_story_stays_blocked(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic Block", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "Story Block",
            "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Block"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/projects/{project.id}/sprints/{sprint['id']}/activate", headers=headers)
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "comprometer"},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "iniciar"},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/blockers",
        json={"description": "impedimento sprint"},
        headers=headers,
    )
    devolver_res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "devolver"},
        headers=headers,
    )
    assert devolver_res.status_code == 200, devolver_res.text

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_after["parent_id"] == epic["id"]
    assert story_after["status"] == "blocked"
    assert story_after["in_product_backlog"] is True
    assert story_after["is_blocked"] is True


def test_rollup_dev_task_to_story(client: TestClient, db):
    project, headers = _scrum_pm(db)

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic3", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task", "title": "Story3", "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=headers,
    ).json()
    dev_task = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task", "title": "Dev task", "parent_id": story["id"],
            "extra": {"scrum_role": "dev"}, "estimacion": 8,
        },
        headers=headers,
    ).json()

    for action in ("move_to_todo", "start", "review", "complete"):
        res = client.post(
            f"/api/v1/projects/{project.id}/records/{dev_task['id']}/transition",
            json={"action_id": action},
            headers=headers,
        )
        assert res.status_code == 200, f"{action} failed: {res.text}"

    story_after = client.get(
        f"/api/v1/projects/{project.id}/records/{story['id']}",
        headers=headers,
    ).json()
    assert story_after["estimacion"] == 8
