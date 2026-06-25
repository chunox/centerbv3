"""
Tests de enforcement de capabilities por rol.
"""
from fastapi.testclient import TestClient

from tests.conftest import make_user, make_org, make_project, make_project_role, make_member, auth_headers


def _waterfall_setup(db, role_slug="dev"):
    pm = make_user(db, email=f"pm_cap_{role_slug}@test.demo", nombre="PM Cap")
    dev = make_user(db, email=f"dev_cap_{role_slug}@test.demo", nombre="Dev Cap")
    org = make_org(db, pm)
    project = make_project(db, org, pm)
    pm_role = make_project_role(db, project, slug="pm", nombre="PM")
    target_role = make_project_role(db, project, slug=role_slug, nombre=role_slug.upper())
    make_member(db, project, pm, pm_role)
    actor = dev if role_slug == "dev" else pm
    if role_slug != "pm":
        make_member(db, project, actor, target_role)
    db.commit()
    return project, auth_headers(actor)


def _scrum_setup(db, role_slug="dev"):
    pm = make_user(db, email=f"pm_scrum_{role_slug}@test.demo", nombre="PM Scrum")
    actor_user = make_user(db, email=f"{role_slug}_scrum@test.demo", nombre=role_slug.upper())
    org = make_org(db, pm)
    project = make_project(
        db, org, pm,
        pack_slug="software-scrum",
        template_slug="t6_scrum_interno",
        delivery_mode="scrum",
    )
    pm_role = make_project_role(db, project, slug="pm", nombre="PM")
    target_role = make_project_role(db, project, slug=role_slug, nombre=role_slug.upper())
    make_member(db, project, pm, pm_role)
    make_member(db, project, actor_user, target_role)
    db.commit()
    return project, auth_headers(actor_user), auth_headers(pm)


def test_dev_cannot_create_milestone(client: TestClient, db):
    project, headers = _waterfall_setup(db, role_slug="dev")
    res = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "milestone", "title": "M1"},
        headers=headers,
    )
    assert res.status_code == 403


def test_dev_can_create_task(client: TestClient, db):
    project, headers = _waterfall_setup(db, role_slug="dev")
    res = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "T1"},
        headers=headers,
    )
    assert res.status_code == 201


def test_qa_cannot_create_dependency(client: TestClient, db):
    pm = make_user(db, email="pm_dep@test.demo", nombre="PM Dep")
    qa = make_user(db, email="qa_dep@test.demo", nombre="QA Dep")
    org = make_org(db, pm)
    project = make_project(db, org, pm)
    pm_role = make_project_role(db, project, slug="pm")
    qa_role = make_project_role(db, project, slug="qa", nombre="QA")
    make_member(db, project, pm, pm_role)
    make_member(db, project, qa, qa_role)
    db.commit()

    t1 = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "T1"},
        headers=auth_headers(pm),
    ).json()
    t2 = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "T2"},
        headers=auth_headers(pm),
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/dependencies",
        json={"predecessor_id": t1["id"], "successor_id": t2["id"]},
        headers=auth_headers(qa),
    )
    assert res.status_code == 403


def test_dev_cannot_add_member(client: TestClient, db):
    project, headers = _waterfall_setup(db, role_slug="dev")
    other = make_user(db, email="other_member@test.demo", nombre="Other")
    db.commit()
    res = client.post(
        f"/api/v1/projects/{project.id}/members",
        json={"email": other.email, "role_slug": "dev"},
        headers=headers,
    )
    assert res.status_code == 403


def test_dev_cannot_update_settings(client: TestClient, db):
    project, headers = _waterfall_setup(db, role_slug="dev")
    res = client.patch(
        f"/api/v1/projects/{project.id}/settings",
        json={"effort_unit": "story_points"},
        headers=headers,
    )
    assert res.status_code == 403


# ─── Scrum capability tests ───────────────────────────────────────────────────

def test_dev_cannot_create_sprint(client: TestClient, db):
    project, headers, _ = _scrum_setup(db, role_slug="dev")
    res = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint Dev"},
        headers=headers,
    )
    assert res.status_code == 403


def test_dev_cannot_create_ceremony(client: TestClient, db):
    project, headers, _ = _scrum_setup(db, role_slug="dev")
    res = client.post(
        f"/api/v1/projects/{project.id}/ceremonies",
        json={"session_type": "daily"},
        headers=headers,
    )
    assert res.status_code == 403


def test_pm_can_create_sprint(client: TestClient, db):
    project, _, pm_headers = _scrum_setup(db, role_slug="dev")
    res = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint PM"},
        headers=pm_headers,
    )
    assert res.status_code == 201


def test_qa_can_revisar_story(client: TestClient, db):
    project, qa_headers, pm_headers = _scrum_setup(db, role_slug="qa")

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic", "extra": {"scrum_role": "epic"}},
        headers=pm_headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task", "title": "Story", "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=pm_headers,
    ).json()
    sprint = client.post(
        f"/api/v1/projects/{project.id}/sprints",
        json={"title": "Sprint QA"},
        headers=pm_headers,
    ).json()
    client.post(f"/api/v1/projects/{project.id}/sprints/{sprint['id']}/activate", headers=pm_headers)
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "comprometer"},
        headers=pm_headers,
    )
    client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "iniciar"},
        headers=pm_headers,
    )

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "revisar"},
        headers=qa_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "in_review"


def test_qa_cannot_comprometer_story(client: TestClient, db):
    project, qa_headers, pm_headers = _scrum_setup(db, role_slug="qa")

    epic = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "Epic2", "extra": {"scrum_role": "epic"}},
        headers=pm_headers,
    ).json()
    story = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "task", "title": "Story2", "parent_id": epic["id"],
            "extra": {"scrum_role": "story"},
        },
        headers=pm_headers,
    ).json()

    res = client.post(
        f"/api/v1/projects/{project.id}/records/{story['id']}/transition",
        json={"action_id": "comprometer"},
        headers=qa_headers,
    )
    assert res.status_code == 403


def test_dev_cannot_delete_dependency(client: TestClient, db):
    pm = make_user(db, email="pm_for_dep@test.demo", nombre="PM For Dep")
    dev = make_user(db, email="dev_dep_del@test.demo", nombre="Dev Dep Del")
    org = make_org(db, pm)
    project = make_project(db, org, pm)
    pm_role = make_project_role(db, project, slug="pm")
    dev_role = make_project_role(db, project, slug="dev", nombre="Dev")
    make_member(db, project, pm, pm_role)
    make_member(db, project, dev, dev_role)
    db.commit()
    dev_headers = auth_headers(dev)
    pm_headers = auth_headers(pm)

    t1 = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "T1"},
        headers=pm_headers,
    ).json()
    t2 = client.post(
        f"/api/v1/projects/{project.id}/records",
        json={"record_type": "task", "title": "T2"},
        headers=pm_headers,
    ).json()
    dep = client.post(
        f"/api/v1/projects/{project.id}/dependencies",
        json={"predecessor_id": t1["id"], "successor_id": t2["id"]},
        headers=pm_headers,
    ).json()

    res = client.delete(
        f"/api/v1/projects/{project.id}/dependencies/{dep['id']}",
        headers=dev_headers,
    )
    assert res.status_code == 403
