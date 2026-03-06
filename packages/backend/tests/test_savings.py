from datetime import date


def test_savings_goals_crud(client, auth_header):
    """Test full CRUD lifecycle for savings goals."""
    # Initially empty
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create goal
    payload = {
        "name": "Emergency Fund",
        "target_amount": 5000.00,
        "currency": "USD",
        "target_date": "2026-12-31",
        "color": "#10B981",
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    goal_id = goal["id"]
    assert goal["name"] == "Emergency Fund"
    assert goal["target_amount"] == 5000.00
    assert goal["current_amount"] == 0
    assert goal["progress"] == 0
    assert goal["color"] == "#10B981"

    # Get single goal
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Emergency Fund"

    # Update goal
    r = client.patch(
        f"/savings/{goal_id}",
        json={"name": "Rainy Day Fund", "target_amount": 3000},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Rainy Day Fund"
    assert r.get_json()["target_amount"] == 3000

    # List has 1
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Delete
    r = client.delete(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200

    # List is empty again
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_savings_contributions(client, auth_header):
    """Test adding contributions and progress tracking."""
    # Create goal
    r = client.post(
        "/savings",
        json={"name": "Vacation", "target_amount": 2000, "currency": "USD"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Add contribution
    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 500, "notes": "First deposit"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["contribution"]["amount"] == 500
    assert data["goal"]["current_amount"] == 500
    assert data["goal"]["progress"] == 25.0

    # Add another contribution
    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 300, "notes": "Second deposit"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["goal"]["current_amount"] == 800
    assert r.get_json()["goal"]["progress"] == 40.0

    # List contributions
    r = client.get(f"/savings/{goal_id}/contributions", headers=auth_header)
    assert r.status_code == 200
    contributions = r.get_json()
    assert len(contributions) == 2


def test_savings_goal_not_found(client, auth_header):
    """Test 404 for nonexistent goal."""
    r = client.get("/savings/9999", headers=auth_header)
    assert r.status_code == 404

    r = client.patch("/savings/9999", json={"name": "x"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/savings/9999", headers=auth_header)
    assert r.status_code == 404


def test_savings_contribution_validation(client, auth_header):
    """Test that contribution amount must be positive."""
    r = client.post(
        "/savings",
        json={"name": "Test", "target_amount": 100},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400

    r = client.post(
        f"/savings/{goal_id}/contribute",
        json={"amount": 0},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_savings_create_validation(client, auth_header):
    """Test that name and target_amount are required."""
    r = client.post("/savings", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 400

    r = client.post("/savings", json={"target_amount": 100}, headers=auth_header)
    assert r.status_code == 400


def test_savings_goal_defaults_to_user_currency(client, auth_header):
    """Test goal uses user's preferred currency when not specified."""
    # Set preferred currency
    client.patch("/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header)

    r = client.post(
        "/savings",
        json={"name": "Euro Fund", "target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


def test_savings_inactive_filter(client, auth_header):
    """Test filtering active/inactive goals."""
    # Create and deactivate a goal
    r = client.post(
        "/savings",
        json={"name": "Old Goal", "target_amount": 100},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]
    client.patch(f"/savings/{goal_id}", json={"active": False}, headers=auth_header)

    # Create active goal
    client.post(
        "/savings",
        json={"name": "Active Goal", "target_amount": 200},
        headers=auth_header,
    )

    # Default: only active
    r = client.get("/savings", headers=auth_header)
    goals = r.get_json()
    assert all(g["active"] for g in goals)

    # All goals
    r = client.get("/savings?active=false", headers=auth_header)
    goals = r.get_json()
    assert len(goals) >= 2
