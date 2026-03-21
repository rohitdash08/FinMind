from datetime import date, timedelta


def test_savings_goals_crud(client, auth_header):
    # Initially empty
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create goal
    payload = {
        "name": "Emergency Fund",
        "target_amount": 5000,
        "current_amount": 500,
        "currency": "USD",
        "deadline": (date.today() + timedelta(days=180)).isoformat(),
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    goal_id = goal["id"]
    assert goal["name"] == "Emergency Fund"
    assert goal["target_amount"] == 5000.0
    assert goal["current_amount"] == 500.0
    assert goal["progress"] == 10.0
    assert goal["status"] == "ACTIVE"
    assert len(goal["milestones"]) == 4
    assert goal["milestones"][0]["percentage"] == 25
    assert goal["milestones"][0]["reached"] is False

    # Get single goal
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == goal_id

    # List has 1
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Update goal
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"name": "Rainy Day Fund", "current_amount": 1500},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Rainy Day Fund"
    assert updated["current_amount"] == 1500.0
    assert updated["progress"] == 30.0
    assert updated["milestones"][0]["reached"] is True  # 25% reached

    # Delete goal
    r = client.delete(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200

    # List is empty again
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_savings_goal_deposit(client, auth_header):
    # Create goal
    r = client.post(
        "/savings-goals",
        json={"name": "Vacation", "target_amount": 1000, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Deposit
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 300},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 300.0
    assert r.get_json()["progress"] == 30.0

    # Deposit to complete
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 800},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 1100.0
    assert data["status"] == "COMPLETED"
    assert all(m["reached"] for m in data["milestones"])

    # Cannot deposit to completed goal
    r = client.post(
        f"/savings-goals/{goal_id}/deposit",
        json={"amount": 50},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_savings_goal_filter_by_status(client, auth_header):
    # Create two goals
    client.post(
        "/savings-goals",
        json={"name": "Goal A", "target_amount": 100},
        headers=auth_header,
    )
    r = client.post(
        "/savings-goals",
        json={"name": "Goal B", "target_amount": 50, "current_amount": 50},
        headers=auth_header,
    )
    # Goal B should auto-complete (current >= target)
    # but auto-complete only happens on update, so let's trigger it
    goal_b_id = r.get_json()["id"]
    client.patch(
        f"/savings-goals/{goal_b_id}",
        json={"current_amount": 50},
        headers=auth_header,
    )

    # Filter active
    r = client.get("/savings-goals?status=ACTIVE", headers=auth_header)
    assert r.status_code == 200
    names = [g["name"] for g in r.get_json()]
    assert "Goal A" in names

    # Filter completed
    r = client.get("/savings-goals?status=COMPLETED", headers=auth_header)
    assert r.status_code == 200
    names = [g["name"] for g in r.get_json()]
    assert "Goal B" in names


def test_savings_goal_validation(client, auth_header):
    # Missing name
    r = client.post(
        "/savings-goals",
        json={"target_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid target_amount
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Not found
    r = client.get("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404

    # Invalid deadline
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": 100, "deadline": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_savings_goal_defaults_to_user_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/savings-goals",
        json={"name": "Euro Goal", "target_amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"
