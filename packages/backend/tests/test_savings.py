from datetime import date


def test_create_savings_goal(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Vacation", "target_amount": 5000, "deadline": "2026-12-31"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Vacation"
    assert data["target_amount"] == 5000
    assert data["current_amount"] == 0
    assert data["progress_pct"] == 0
    assert data["completed"] is False


def test_list_goals_with_progress(client, auth_header):
    client.post(
        "/savings/goals",
        json={"name": "Car", "target_amount": 20000},
        headers=auth_header,
    )
    client.post(
        "/savings/goals",
        json={"name": "House", "target_amount": 100000},
        headers=auth_header,
    )
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    goals = r.get_json()
    assert len(goals) == 2
    for g in goals:
        assert "progress_pct" in g


def test_deposit_updates_amount(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Phone", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{goal_id}/deposit",
        json={"amount": 250, "note": "first deposit"},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 250
    assert data["progress_pct"] == 25.0


def test_goal_completion_on_target_reached(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Gift", "target_amount": 100},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{goal_id}/deposit",
        json={"amount": 100},
        headers=auth_header,
    )
    data = r.get_json()
    assert data["completed"] is True
    assert data["completed_at"] is not None


def test_milestones_calculation(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Laptop", "target_amount": 2000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Deposit 50% of target
    client.post(
        f"/savings/goals/{goal_id}/deposit",
        json={"amount": 1000},
        headers=auth_header,
    )

    r = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    milestones = data["milestones"]
    assert len(milestones) == 4
    assert milestones[0] == {"percent": 25, "reached": True}
    assert milestones[1] == {"percent": 50, "reached": True}
    assert milestones[2] == {"percent": 75, "reached": False}
    assert milestones[3] == {"percent": 100, "reached": False}


def test_withdraw_from_goal(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Fund", "target_amount": 500},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    client.post(
        f"/savings/goals/{goal_id}/deposit",
        json={"amount": 300},
        headers=auth_header,
    )

    r = client.post(
        f"/savings/goals/{goal_id}/withdraw",
        json={"amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 200


def test_cannot_access_other_user_goals(client, auth_header):
    # Create a goal with the default user
    r = client.post(
        "/savings/goals",
        json={"name": "Secret", "target_amount": 999},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Register a second user
    client.post(
        "/auth/register",
        json={"email": "other@example.com", "password": "password123"},
    )
    r2 = client.post(
        "/auth/login",
        json={"email": "other@example.com", "password": "password123"},
    )
    other_header = {"Authorization": f"Bearer {r2.get_json()['access_token']}"}

    # Second user cannot see first user's goal
    r = client.get(f"/savings/goals/{goal_id}", headers=other_header)
    assert r.status_code == 404


def test_requires_auth(client):
    r = client.get("/savings/goals")
    assert r.status_code == 401
