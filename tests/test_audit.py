"""
Tests de audit log — operaciones sensibles aparecen en activity feed.
"""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _scrum_project(db):
    pm = make_user(db, email="pm_audit@test.demo", nombre="PM Audit")
    other = make_user(db, email="other_audit@test.demo", nombre="Other Audit")
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
    db.commit()
    return project, pm, other, auth_headers(pm)


def test_member_add_appears_in_activity(client: TestClient, db):
    project, pm, other, headers = _scrum_project(db)

    res = client.post(
        f"/api/v1/projects/{project.id}/members",
        json={"email": other.email, "role_slug": "dev"},
        headers=headers,
    )
    assert res.status_code == 201

    activity = client.get(f"/api/v1/projects/{project.id}/activity", headers=headers).json()
    actions = [item["action"] for item in activity["items"]]
    assert "member_added" in actions


def test_sprint_activate_appears_in_activity(client: TestClient, db):
    project, _, _, headers = _scrum_project(db)

    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Audit"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project.id}/sprints/{sprint['id']}/activate",
        headers=headers,
    )

    activity = client.get(f"/api/v1/projects/{project.id}/activity", headers=headers).json()
    actions = [item["action"] for item in activity["items"]]
    assert "activated" in actions


def test_record_update_appears_in_activity(client: TestClient, db):
    project, _, _, headers = _scrum_project(db)

    record = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Original", "extra": {"scrum_role": "epic"}},
        headers=headers,
    ).json()
    client.patch(
        f"/api/v1/projects/{project.id}/records/{record['id']}",
        json={"title": "Actualizado"},
        headers=headers,
    )

    activity = client.get(f"/api/v1/projects/{project.id}/activity", headers=headers).json()
    actions = [item["action"] for item in activity["items"]]
    assert "updated" in actions
