"""
Tests de records — CRUD completo, transiciones, bloqueantes, dependencias.
"""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    auth_headers, make_member, make_org, make_project,
    make_project_role, make_user,
)


def _create_record(client: TestClient, project_id: str, headers: dict, **kwargs) -> dict:
    body = {"record_type": "feature", "title": "Test feature", "status": "pendiente", **kwargs}
    res = client.post(f"/api/v1/projects/{project_id}/records", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def test_list_records_requires_membership(client: TestClient, project_with_pm):
    # Otro usuario sin membresía
    other = {"Authorization": "Bearer invalidtoken"}
    res = client.get(f"/api/v1/projects/{project_with_pm['project'].id}/records", headers=other)
    assert res.status_code in (401, 403)


def test_list_records_empty(client: TestClient, project_with_pm):
    res = client.get(
        f"/api/v1/projects/{project_with_pm['project'].id}/records",
        headers=project_with_pm["headers"],
    )
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["has_more"] is False


def test_create_record(client: TestClient, project_with_pm):
    record = _create_record(client, project_with_pm["project"].id, project_with_pm["headers"])
    assert record["id"]
    assert record["title"] == "Test feature"
    assert record["status"] == "pendiente"


def test_get_record(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    record = _create_record(client, project_id, project_with_pm["headers"])
    res = client.get(f"/api/v1/projects/{project_id}/records/{record['id']}", headers=project_with_pm["headers"])
    assert res.status_code == 200
    assert res.json()["id"] == record["id"]


def test_update_record(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    record = _create_record(client, project_id, project_with_pm["headers"])
    res = client.patch(
        f"/api/v1/projects/{project_id}/records/{record['id']}",
        json={"title": "Updated title"},
        headers=project_with_pm["headers"],
    )
    assert res.status_code == 200
    assert res.json()["title"] == "Updated title"


def test_delete_record(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    record = _create_record(client, project_id, project_with_pm["headers"])
    res = client.delete(
        f"/api/v1/projects/{project_id}/records/{record['id']}",
        headers=project_with_pm["headers"],
    )
    assert res.status_code == 204


def test_filter_records_by_type(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]
    _create_record(client, project_id, headers, record_type="feature")
    _create_record(client, project_id, headers, record_type="task", title="A task")
    res = client.get(f"/api/v1/projects/{project_id}/records?record_type=task", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert all(r["record_type"] == "task" for r in data["items"])


# ─── Bloqueantes ──────────────────────────────────────────────────────────────

def test_create_and_list_blocker(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]
    record = _create_record(client, project_id, headers)

    res = client.post(
        f"/api/v1/projects/{project_id}/records/{record['id']}/blockers",
        json={"description": "Dependencia externa bloqueante"},
        headers=headers,
    )
    assert res.status_code == 201
    blocker = res.json()
    assert blocker["is_resolved"] is False

    res = client.get(
        f"/api/v1/projects/{project_id}/records/{record['id']}/blockers",
        headers=headers,
    )
    assert len(res.json()) == 1


def test_resolve_blocker(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]
    record = _create_record(client, project_id, headers)

    blocker_res = client.post(
        f"/api/v1/projects/{project_id}/records/{record['id']}/blockers",
        json={"description": "bloqueante"},
        headers=headers,
    )
    blocker_id = blocker_res.json()["id"]

    res = client.post(
        f"/api/v1/projects/{project_id}/records/{record['id']}/blockers/{blocker_id}/resolve",
        json={"resolution_note": "Resuelto en reunión"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["is_resolved"] is True


def test_dev_can_resolve_blocker(client: TestClient, db):
    from tests.conftest import (
        auth_headers,
        make_member,
        make_org,
        make_project,
        make_project_role,
        make_user,
    )

    pm = make_user(db, email="pm_devblock@test.demo", nombre="PM")
    dev = make_user(db, email="devblock@test.demo", nombre="Dev")
    org = make_org(db, pm)
    project = make_project(db, org, pm)
    pm_role = make_project_role(db, project, slug="pm", nombre="PM")
    dev_role = make_project_role(db, project, slug="dev", nombre="Dev")
    make_member(db, project, pm, pm_role)
    make_member(db, project, dev, dev_role)
    db.commit()

    pm_headers = auth_headers(pm)
    dev_headers = auth_headers(dev)
    project_id = project.id

    record = client.post(
        f"/api/v1/projects/{project_id}/records",
        json={"record_type": "feature", "title": "Blocked", "status": "pendiente"},
        headers=pm_headers,
    ).json()

    blocker_res = client.post(
        f"/api/v1/projects/{project_id}/records/{record['id']}/blockers",
        json={"description": "impedimento"},
        headers=pm_headers,
    )
    blocker_id = blocker_res.json()["id"]

    res = client.post(
        f"/api/v1/projects/{project_id}/records/{record['id']}/blockers/{blocker_id}/resolve",
        json={"resolution_note": "listo"},
        headers=dev_headers,
    )
    assert res.status_code == 200
    assert res.json()["is_resolved"] is True


# ─── Dependencias ─────────────────────────────────────────────────────────────

def test_create_dependency(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]
    r1 = _create_record(client, project_id, headers, title="R1")
    r2 = _create_record(client, project_id, headers, title="R2")

    res = client.post(
        f"/api/v1/projects/{project_id}/dependencies",
        json={"predecessor_id": r1["id"], "successor_id": r2["id"]},
        headers=headers,
    )
    assert res.status_code == 201
    dep = res.json()
    assert dep["predecessor_id"] == r1["id"]


def test_list_dependencies(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]
    r1 = _create_record(client, project_id, headers, title="R1")
    r2 = _create_record(client, project_id, headers, title="R2")

    client.post(
        f"/api/v1/projects/{project_id}/dependencies",
        json={"predecessor_id": r1["id"], "successor_id": r2["id"]},
        headers=headers,
    )

    res = client.get(f"/api/v1/projects/{project_id}/records/{r2['id']}/dependencies", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data["predecessors"]) == 1
    assert data["predecessors"][0]["predecessor_id"] == r1["id"]
