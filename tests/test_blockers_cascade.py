"""
Tests de cascada de bloqueantes — gate not_blocked con herencia de ancestros.
"""
from fastapi.testclient import TestClient


def _create(client: TestClient, project_id: str, headers: dict, **kwargs) -> dict:
    body = {"record_type": "feature", "title": "Feature", "status": "pendiente", **kwargs}
    res = client.post(f"/api/v1/projects/{project_id}/records", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _block(client: TestClient, project_id: str, record_id: str, headers: dict) -> None:
    res = client.post(
        f"/api/v1/projects/{project_id}/records/{record_id}/blockers",
        json={"description": "Bloqueo de prueba"},
        headers=headers,
    )
    assert res.status_code == 201, res.text


def _transition(client: TestClient, project_id: str, record_id: str, action_id: str, headers: dict):
    return client.post(
        f"/api/v1/projects/{project_id}/records/{record_id}/transition",
        json={"action_id": action_id},
        headers=headers,
    )


def test_parent_blocker_blocks_child_transition(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]

    feature = _create(client, project_id, headers)
    task_res = client.post(
        f"/api/v1/projects/{project_id}/records",
        json={
            "record_type": "task",
            "title": "Task hijo",
            "parent_id": feature["id"],
            "status": "to_do",
        },
        headers=headers,
    )
    assert task_res.status_code == 201
    task = task_res.json()

    _block(client, project_id, feature["id"], headers)

    res = _transition(client, project_id, task["id"], "start", headers)
    assert res.status_code == 422
    detail = res.json()["detail"].lower()
    assert "bloqueador" in detail or "blocked" in detail


def test_resolved_parent_unblocks_child(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]

    feature = _create(client, project_id, headers)
    task_res = client.post(
        f"/api/v1/projects/{project_id}/records",
        json={
            "record_type": "task",
            "title": "Task hijo",
            "parent_id": feature["id"],
            "status": "to_do",
        },
        headers=headers,
    )
    task = task_res.json()

    blocker_res = client.post(
        f"/api/v1/projects/{project_id}/records/{feature['id']}/blockers",
        json={"description": "temp"},
        headers=headers,
    )
    blocker_id = blocker_res.json()["id"]

    client.post(
        f"/api/v1/projects/{project_id}/records/{feature['id']}/blockers/{blocker_id}/resolve",
        json={},
        headers=headers,
    )

    res = _transition(client, project_id, task["id"], "start", headers)
    assert res.status_code == 200


def test_child_own_blocker_persists_after_parent_resolved(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]

    feature = _create(client, project_id, headers)
    task_res = client.post(
        f"/api/v1/projects/{project_id}/records",
        json={
            "record_type": "task",
            "title": "Task hijo",
            "parent_id": feature["id"],
            "status": "to_do",
        },
        headers=headers,
    )
    task = task_res.json()

    _block(client, project_id, feature["id"], headers)
    _block(client, project_id, task["id"], headers)

    blockers = client.get(
        f"/api/v1/projects/{project_id}/records/{feature['id']}/blockers",
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/projects/{project_id}/records/{feature['id']}/blockers/{blockers[0]['id']}/resolve",
        json={},
        headers=headers,
    )

    res = _transition(client, project_id, task["id"], "start", headers)
    assert res.status_code == 422


def test_record_response_is_blocked_inherited(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]

    feature = _create(client, project_id, headers)
    task_res = client.post(
        f"/api/v1/projects/{project_id}/records",
        json={
            "record_type": "task",
            "title": "Task hijo",
            "parent_id": feature["id"],
            "status": "to_do",
        },
        headers=headers,
    )
    task = task_res.json()
    assert task.get("is_blocked") is False

    _block(client, project_id, feature["id"], headers)

    get_res = client.get(
        f"/api/v1/projects/{project_id}/records/{task['id']}",
        headers=headers,
    )
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["is_blocked"] is True
    assert data["status"] == "blocked"
    assert data["extra"].get("blocked_by_inheritance") is True
    assert len(data["active_blockers"]) == 0

    feature_res = client.get(
        f"/api/v1/projects/{project_id}/records/{feature['id']}",
        headers=headers,
    ).json()
    assert feature_res["status"] == "blocked"
    assert len(feature_res["active_blockers"]) == 1
