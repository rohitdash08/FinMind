from datetime import date, timedelta


def test_savings_goals_initially_empty(client, auth_header):
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_savings_goal(client, auth_header):
    payload = {
        "name": "Emergency Fund",
        "target_amount": 10000.00,
        "deadline": (date.today() + timedelta(days=365)).isoformat(),
    }
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["id"] is not None
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 10000.0
    assert data["current_amount"] == 0.0
    assert data["progress_pct"] == 0.0
    assert data["status"] == "ACTIVE"
    assert data["deadline"] is not None


def test_create_savings_goal_no_deadline(client, auth_header):
    payload = {"name": "Vacation", "target_amount": 5000.0}
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["deadline"] is None


def test_create_savings_goal_missing_fields(client, auth_header):
    r = client.post("/savings/goals", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 400

    r = client.post("/savings/goals", json={"target_amount": 100}, headers=auth_header)
    assert r.status_code == 400


def test_list_savings_goals(client, auth_header):
    client.post(
        "/savings/goals",
        json={"name": "Goal A", "target_amount": 1000},
        headers=auth_header,
    )
    client.post(
        "/savings/goals",
        json={"name": "Goal B", "target_amount": 2000},
        headers=auth_header,
    )
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 2
    names = {i["name"] for i in items}
    assert "Goal A" in names
    assert "Goal B" in names


def test_get_savings_goal(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "House", "target_amount": 50000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "House"


def test_get_savings_goal_not_found(client, auth_header):
    r = client.get("/savings/goals/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_savings_goal(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Old Name", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.put(
        f"/savings/goals/{goal_id}",
        json={"name": "New Name", "target_amount": 2000},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "New Name"
    assert data["target_amount"] == 2000.0


def test_update_savings_goal_status(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Goal", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.put(
        f"/savings/goals/{goal_id}", json={"status": "PAUSED"}, headers=auth_header
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "PAUSED"


def test_delete_savings_goal(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "To Delete", "target_amount": 500},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.delete(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    r = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 404


def test_contribute_to_savings_goal(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Car", "target_amount": 5000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 500.0
    assert data["progress_pct"] == 10.0
    assert data["status"] == "ACTIVE"


def test_contribute_accumulates(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Laptop", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 300},
        headers=auth_header,
    )
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 400},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 700.0


def test_contribute_auto_completes_goal(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Phone", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "COMPLETED"
    assert data["progress_pct"] == 100.0


def test_contribute_invalid_amount(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Test", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400

    r = client.post(
        f"/savings/goals/{goal_id}/contribute", json={"amount": 0}, headers=auth_header
    )
    assert r.status_code == 400


def test_goals_isolated_between_users(client):
    # Register two users
    client.post(
        "/auth/register", json={"email": "user1@test.com", "password": "pass123"}
    )
    client.post(
        "/auth/register", json={"email": "user2@test.com", "password": "pass123"}
    )

    r = client.post(
        "/auth/login", json={"email": "user1@test.com", "password": "pass123"}
    )
    header1 = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    r = client.post(
        "/auth/login", json={"email": "user2@test.com", "password": "pass123"}
    )
    header2 = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    # User1 creates a goal
    r = client.post(
        "/savings/goals",
        json={"name": "Private Goal", "target_amount": 1000},
        headers=header1,
    )
    goal_id = r.get_json()["id"]

    # User2 cannot see it
    r = client.get("/savings/goals", headers=header2)
    assert r.get_json() == []

    # User2 cannot access it directly
    r = client.get(f"/savings/goals/{goal_id}", headers=header2)
    assert r.status_code == 404
