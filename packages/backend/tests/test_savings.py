import pytest
import json
from datetime import date, timedelta


def test_create_goal(client, auth_headers):
    resp = client.post(
        "/savings",
        headers=auth_headers,
        json={"name": "Vacation Fund", "target_amount": "5000", "currency": "EUR", "deadline": "2026-12-31"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "Vacation Fund"
    assert data["target_amount"] == "5000"
    assert data["current_amount"] == "0"
    assert data["progress_percent"] == 0
    assert data["is_completed"] is False
    assert data["milestones"] == [
        {"percent": 25, "reached": False},
        {"percent": 50, "reached": False},
        {"percent": 75, "reached": False},
        {"percent": 100, "reached": False},
    ]


def test_create_goal_with_initial_amount(client, auth_headers):
    resp = client.post(
        "/savings",
        headers=auth_headers,
        json={"name": "Emergency Fund", "target_amount": "10000", "current_amount": "2500"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["current_amount"] == "2500"
    assert data["progress_percent"] == 25.0
    assert data["milestones"][0]["reached"] is True
    assert data["milestones"][1]["reached"] is False


def test_create_goal_missing_fields(client, auth_headers):
    resp = client.post("/savings", headers=auth_headers, json={})
    assert resp.status_code == 400


def test_list_goals(client, auth_headers):
    client.post("/savings", headers=auth_headers, json={"name": "Goal 1", "target_amount": "1000"})
    client.post("/savings", headers=auth_headers, json={"name": "Goal 2", "target_amount": "2000"})
    resp = client.get("/savings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["goals"]) == 2


def test_get_goal_detail(client, auth_headers):
    create = client.post("/savings", headers=auth_headers, json={"name": "Test Goal", "target_amount": "1000"})
    goal_id = create.get_json()["id"]
    resp = client.get(f"/savings/{goal_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["goal"]["name"] == "Test Goal"
    assert data["contributions"] == []


def test_update_goal(client, auth_headers):
    create = client.post("/savings", headers=auth_headers, json={"name": "Old Name", "target_amount": "1000"})
    goal_id = create.get_json()["id"]
    resp = client.put(f"/savings/{goal_id}", headers=auth_headers, json={"name": "New Name", "target_amount": "2000"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "New Name"
    assert resp.get_json()["target_amount"] == "2000"


def test_delete_goal(client, auth_headers):
    create = client.post("/savings", headers=auth_headers, json={"name": "Delete Me", "target_amount": "500"})
    goal_id = create.get_json()["id"]
    resp = client.delete(f"/savings/{goal_id}", headers=auth_headers)
    assert resp.status_code == 200
    resp = client.get(f"/savings/{goal_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_add_contribution(client, auth_headers):
    create = client.post("/savings", headers=auth_headers, json={"name": "Save", "target_amount": "1000"})
    goal_id = create.get_json()["id"]
    resp = client.post(
        f"/savings/{goal_id}/contributions",
        headers=auth_headers,
        json={"amount": "250", "notes": "Monthly deposit"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["contribution"]["amount"] == "250"
    assert data["goal"]["current_amount"] == "250"
    assert data["goal"]["progress_percent"] == 25.0
    assert data["goal"]["milestones"][0]["reached"] is True


def test_contribution_completes_goal(client, auth_headers):
    create = client.post("/savings", headers=auth_headers, json={"name": "Small Goal", "target_amount": "100"})
    goal_id = create.get_json()["id"]
    resp = client.post(
        f"/savings/{goal_id}/contributions",
        headers=auth_headers,
        json={"amount": "100"},
    )
    data = resp.get_json()
    assert data["goal"]["is_completed"] is True
    assert data["goal"]["progress_percent"] == 100.0


def test_delete_contribution(client, auth_headers):
    create = client.post("/savings", headers=auth_headers, json={"name": "Test", "target_amount": "1000"})
    goal_id = create.get_json()["id"]
    contrib = client.post(f"/savings/{goal_id}/contributions", headers=auth_headers, json={"amount": "500"})
    contrib_id = contrib.get_json()["contribution"]["id"]
    resp = client.delete(f"/savings/{goal_id}/contributions/{contrib_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["goal"]["current_amount"] == "0"


def test_goal_not_found(client, auth_headers):
    resp = client.get("/savings/9999", headers=auth_headers)
    assert resp.status_code == 404


def test_unauthorized_access(client):
    resp = client.get("/savings")
    assert resp.status_code in (401, 422)
