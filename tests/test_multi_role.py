"""
Tests de multi-rol — unión de capabilities cuando el actor tiene varios roles.
"""
from fastapi.testclient import TestClient

from tests.conftest import (
    auth_headers,
    make_member,
    make_org,
    make_project,
    make_project_role,
    make_user,
)


def test_multi_role_merged_capabilities(client: TestClient, db):
    user = make_user(db, email="multi@test.demo", nombre="Multi Role")
    org = make_org(db, user)
    project = make_project(db, org, user)
    pm_role = make_project_role(db, project, slug="pm", nombre="PM")
    dev_role = make_project_role(db, project, slug="dev", nombre="Dev")
    make_member(db, project, user, pm_role)
    make_member(db, project, user, dev_role)
    db.commit()
    headers = auth_headers(user)

    res = client.get(f"/api/v1/projects/{project.id}/access-context", headers=headers)
    assert res.status_code == 200
    data = res.json()
    caps = set(data["capabilities"])
    assert "workbench.settings" in caps
    assert "record.task.transition.move" in caps
    assert data["role_slug"] == "pm"


def test_multi_role_can_use_dev_transition(client: TestClient, db):
    user = make_user(db, email="multi2@test.demo", nombre="Multi Role 2")
    org = make_org(db, user)
    project = make_project(db, org, user)
    pm_role = make_project_role(db, project, slug="pm", nombre="PM")
    dev_role = make_project_role(db, project, slug="dev", nombre="Dev")
    make_member(db, project, user, pm_role)
    make_member(db, project, user, dev_role)
    db.commit()
    headers = auth_headers(user)

    feature_res = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "feature", "title": "F", "status": "pendiente"},
        headers=headers,
    )
    assert feature_res.status_code == 201
    feature = feature_res.json()

    task_res = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task",
            "title": "T",
            "parent_id": feature["id"],
            "status": "to_do",
        },
        headers=headers,
    )
    task = task_res.json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{task['id']}/transition",
        json={"action_id": "start"},
        headers=headers,
    )
    assert res.status_code == 200
