"""
Tests de paginación de records — total, has_more, offset.
"""
from fastapi.testclient import TestClient


def test_list_records_pagination(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]

    for i in range(12):
        res = client.post(
            f"/api/v1/projects/{project_id}/records",
            json={"record_type": "task", "title": f"Task {i}", "status": "backlog"},
            headers=headers,
        )
        assert res.status_code == 201

    page1 = client.get(
        f"/api/v1/projects/{project_id}/records?limit=5&offset=0",
        headers=headers,
    )
    assert page1.status_code == 200
    data1 = page1.json()
    assert data1["total"] == 12
    assert len(data1["items"]) == 5
    assert data1["has_more"] is True
    assert data1["limit"] == 5
    assert data1["offset"] == 0

    page2 = client.get(
        f"/api/v1/projects/{project_id}/records?limit=5&offset=5",
        headers=headers,
    )
    data2 = page2.json()
    assert len(data2["items"]) == 5
    assert data2["has_more"] is True

    page3 = client.get(
        f"/api/v1/projects/{project_id}/records?limit=5&offset=10",
        headers=headers,
    )
    data3 = page3.json()
    assert len(data3["items"]) == 2
    assert data3["has_more"] is False


def test_search_by_title(client: TestClient, project_with_pm):
    project_id = project_with_pm["project"].id
    headers = project_with_pm["headers"]

    client.post(
        f"/api/v1/projects/{project_id}/records",
        json={"record_type": "feature", "title": "Login OAuth", "status": "pendiente"},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project_id}/records",
        json={"record_type": "feature", "title": "Dashboard KPI", "status": "pendiente"},
        headers=headers,
    )

    res = client.get(
        f"/api/v1/projects/{project_id}/records?q=oauth",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Login OAuth"
