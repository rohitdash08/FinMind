from datetime import date


def test_savings_goals_crud(client, auth_header):
    # Initially empty
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create goal
    payload = {
        "name": "Emergency Fund",
        "target_amount": 5000.00,
        "currency": "USD",
        "target_date": "2025-12-31",
        "icon": "shield",
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    goal_id = goal["id"]
    assert goal["name"] == "Emergency Fund"
    assert goal["target_amount"] == 5000.00
    assert goal["current_amount"] == 0
    assert goal["progress_pct"] == 0
    assert goal["milestones_achieved"] == []
    assert goal["icon"] == "shield"

    # List has 1
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == goal_id

    # Get single
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Emergency Fund"

    # Update
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"name": "Rainy Day Fund", "target_amount": 6000},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Rainy Day Fund"
    assert r.get_json()["target_amount"] == 6000.0

    # Delete
    r = client.delete(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # List empty again
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_savings_goal_validation(client, auth_header):
    # Missing required fields
    r = client.post("/savings-goals", json={}, headers=auth_header)
    assert r.status_code == 400

    # Negative target
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Not found
    r = client.get("/savings-goals/9999", headers=auth_header)
    assert r.status_code == 404


def test_contributions_and_milestones(client, auth_header):
    # Create goal
    r = client.post(
        "/savings-goals",
        json={"name": "Vacation", "target_amount": 1000.00, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Contribute 250 (25% milestone)
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 250, "notes": "First deposit"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["contribution"]["amount"] == 250
    assert data["goal"]["current_amount"] == 250
    assert data["goal"]["progress_pct"] == 25.0
    assert 25 in data["goal"]["milestones_achieved"]
    assert 25 in data["new_milestones"]

    # Contribute another 250 (50% milestone)
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 250},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["goal"]["current_amount"] == 500
    assert data["goal"]["progress_pct"] == 50.0
    assert 50 in data["goal"]["milestones_achieved"]

    # List contributions
    r = client.get(f"/savings-goals/{goal_id}/contributions", headers=auth_header)
    assert r.status_code == 200
    contribs = r.get_json()
    assert len(contribs) == 2

    # Contribution validation
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": -10},
        headers=auth_header,
    )
    assert r.status_code == 400

    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_withdraw(client, auth_header):
    # Create goal with initial amount
    r = client.post(
        "/savings-goals",
        json={"name": "Car", "target_amount": 2000, "current_amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Withdraw 200
    r = client.post(
        f"/savings-goals/{goal_id}/withdraw",
        json={"amount": 200, "notes": "Emergency"},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["goal"]["current_amount"] == 300
    assert data["contribution"]["amount"] == -200

    # Over-withdraw fails
    r = client.post(
        f"/savings-goals/{goal_id}/withdraw",
        json={"amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "insufficient" in r.get_json()["error"]


def test_goal_defaults_to_user_preferred_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/savings-goals",
        json={"name": "Travel", "target_amount": 3000},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


def test_include_completed_filter(client, auth_header):
    # Create and deactivate a goal
    r = client.post(
        "/savings-goals",
        json={"name": "Done Goal", "target_amount": 100},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]
    client.patch(
        f"/savings-goals/{goal_id}",
        json={"active": False},
        headers=auth_header,
    )

    # Default list excludes inactive
    r = client.get("/savings-goals", headers=auth_header)
    assert len(r.get_json()) == 0

    # With include_completed
    r = client.get("/savings-goals?include_completed=true", headers=auth_header)
    assert len(r.get_json()) == 1
