"""Tests for savings goals."""


def _auth_header(client):
    email = "savings@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_savings_goal(client):
    headers = _auth_header(client)
    r = client.post(
        "/savings/",
        json={"name": "Emergency Fund", "target_amount": 10000, "currency": "USD"},
        headers=headers,
    )
    assert r.status_code == 201
    data = r.get_json()["goal"]
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 10000
    assert data["current_amount"] == 0
    assert data["progress_percent"] == 0
    assert data["achieved"] is False


def test_list_savings_goals(client):
    headers = _auth_header(client)
    client.post(
        "/savings/",
        json={"name": "Vacation", "target_amount": 5000},
        headers=headers,
    )
    r = client.get("/savings/", headers=headers)
    assert r.status_code == 200
    assert len(r.get_json()["goals"]) >= 1


def test_contribute_to_goal(client):
    headers = _auth_header(client)
    r = client.post(
        "/savings/",
        json={"name": "Car", "target_amount": 1000},
        headers=headers,
    )
    goal_id = r.get_json()["goal"]["id"]

    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 500, "notes": "First deposit"},
        headers=headers,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["goal"]["current_amount"] == 500
    assert data["goal"]["progress_percent"] == 50.0
    assert data["goal"]["achieved"] is False


def test_goal_achieved_on_target(client):
    headers = _auth_header(client)
    r = client.post(
        "/savings/",
        json={"name": "Phone", "target_amount": 100},
        headers=headers,
    )
    goal_id = r.get_json()["goal"]["id"]

    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 100},
        headers=headers,
    )
    assert r.status_code == 201
    data = r.get_json()["goal"]
    assert data["achieved"] is True
    assert data["achieved_at"] is not None
    assert data["progress_percent"] == 100.0


def test_delete_goal(client):
    headers = _auth_header(client)
    r = client.post(
        "/savings/",
        json={"name": "Delete me", "target_amount": 50},
        headers=headers,
    )
    goal_id = r.get_json()["goal"]["id"]

    r = client.delete(f"/savings/{goal_id}", headers=headers)
    assert r.status_code == 200

    r = client.get(f"/savings/{goal_id}", headers=headers)
    assert r.status_code == 404
