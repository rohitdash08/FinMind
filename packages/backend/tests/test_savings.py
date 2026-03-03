"""Tests for savings goal tracking & milestones (issue #133)."""


def test_create_savings_goal(client, auth_header):
    r = client.post(
        "/savings/",
        json={"name": "Emergency Fund", "target_amount": 10000, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 10000
    assert data["saved_amount"] == 0
    assert data["progress_pct"] == 0
    assert data["completed"] is False
    assert len(data["milestones"]) == 4


def test_create_goal_requires_fields(client, auth_header):
    r = client.post("/savings/", json={}, headers=auth_header)
    assert r.status_code == 400

    r = client.post(
        "/savings/", json={"name": "X"}, headers=auth_header
    )
    assert r.status_code == 400


def test_list_goals(client, auth_header):
    client.post(
        "/savings/",
        json={"name": "Vacation", "target_amount": 5000},
        headers=auth_header,
    )
    client.post(
        "/savings/",
        json={"name": "Car", "target_amount": 20000},
        headers=auth_header,
    )
    r = client.get("/savings/", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 2


def test_deposit_updates_progress(client, auth_header):
    r = client.post(
        "/savings/",
        json={"name": "Laptop", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Deposit 250 (25%)
    r = client.post(
        f"/savings/{goal_id}/deposit",
        json={"amount": 250, "notes": "First deposit"},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["saved_amount"] == 250
    assert data["progress_pct"] == 25.0
    assert data["milestones"][0]["reached"] is True  # 25%
    assert data["milestones"][1]["reached"] is False  # 50%


def test_milestones_all_reached(client, auth_header):
    r = client.post(
        "/savings/",
        json={"name": "Phone", "target_amount": 100},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Deposit full amount
    r = client.post(
        f"/savings/{goal_id}/deposit",
        json={"amount": 100},
        headers=auth_header,
    )
    data = r.get_json()
    assert data["completed"] is True
    assert data["progress_pct"] == 100.0
    assert all(m["reached"] for m in data["milestones"])


def test_delete_goal(client, auth_header):
    r = client.post(
        "/savings/",
        json={"name": "Delete Me", "target_amount": 500},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]
    r = client.delete(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 404


def test_deposit_nonexistent_goal(client, auth_header):
    r = client.post(
        "/savings/99999/deposit",
        json={"amount": 50},
        headers=auth_header,
    )
    assert r.status_code == 404
