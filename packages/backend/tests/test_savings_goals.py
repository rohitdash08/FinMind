from datetime import date, timedelta


def test_savings_goals_crud(client, auth_header):
    """Test full CRUD lifecycle for savings goals."""
    # Initially empty
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create a goal
    payload = {
        "name": "Emergency Fund",
        "target_amount": 10000,
        "category": "EMERGENCY",
        "deadline": (date.today() + timedelta(days=365)).isoformat(),
        "notes": "6 months of expenses",
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # List shows 1 goal
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == goal_id
    assert items[0]["name"] == "Emergency Fund"
    assert items[0]["target_amount"] == 10000
    assert items[0]["current_amount"] == 0
    assert items[0]["progress_percentage"] == 0

    # Get single goal with details
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert detail["name"] == "Emergency Fund"
    assert len(detail["milestones"]) == 4  # Default milestones

    # Update the goal
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"name": "Emergency Fund v2", "target_amount": 15000},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Emergency Fund v2"
    assert r.get_json()["target_amount"] == 15000

    # Delete the goal
    r = client.delete(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # Verify deleted
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_savings_goal_not_found(client, auth_header):
    """Test 404 for non-existent goal."""
    r = client.get("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404


def test_create_goal_validation(client, auth_header):
    """Test validation on create."""
    # Missing name
    r = client.post(
        "/savings-goals", json={"target_amount": 1000}, headers=auth_header
    )
    assert r.status_code == 400

    # Missing target
    r = client.post("/savings-goals", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 400

    # Negative target
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid category
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": 1000, "category": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_contributions_and_milestones(client, auth_header):
    """Test adding contributions and milestone tracking."""
    # Create a goal
    r = client.post(
        "/savings-goals",
        json={"name": "Vacation", "target_amount": 1000, "category": "VACATION"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Add contribution - hits 25% milestone
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 250, "notes": "First deposit"},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 250
    assert data["progress_percentage"] == 25.0
    assert len(data["newly_reached_milestones"]) == 1
    assert data["newly_reached_milestones"][0]["title"] == "Getting Started"

    # Add another contribution - hits 50%
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 250},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 500
    assert data["progress_percentage"] == 50.0
    assert len(data["newly_reached_milestones"]) == 1
    assert data["newly_reached_milestones"][0]["title"] == "Halfway There"

    # List contributions
    r = client.get(f"/savings-goals/{goal_id}/contributions", headers=auth_header)
    assert r.status_code == 200
    contribs = r.get_json()
    assert len(contribs) == 2

    # Complete the goal
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 1000
    assert data["progress_percentage"] == 100
    assert data["status"] == "COMPLETED"
    assert len(data["newly_reached_milestones"]) == 2  # 75% and 100%


def test_withdrawal(client, auth_header):
    """Test withdrawing from a goal."""
    # Create and fund a goal
    r = client.post(
        "/savings-goals",
        json={"name": "Car Fund", "target_amount": 5000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 1000},
        headers=auth_header,
    )

    # Withdraw
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 300, "type": "WITHDRAWAL", "notes": "Emergency expense"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 700

    # Try to withdraw more than available
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 800, "type": "WITHDRAWAL"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "exceeds" in r.get_json()["error"]


def test_contribution_to_inactive_goal(client, auth_header):
    """Test contributing to cancelled/completed goal fails."""
    r = client.post(
        "/savings-goals",
        json={"name": "Old Goal", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Cancel the goal
    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"status": "CANCELLED"},
        headers=auth_header,
    )
    assert r.status_code == 200

    # Try to contribute
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "not active" in r.get_json()["error"]


def test_goals_summary(client, auth_header):
    """Test summary endpoint."""
    # Create two goals with contributions
    r = client.post(
        "/savings-goals",
        json={"name": "Goal A", "target_amount": 1000},
        headers=auth_header,
    )
    goal_a = r.get_json()["id"]

    r = client.post(
        "/savings-goals",
        json={"name": "Goal B", "target_amount": 2000},
        headers=auth_header,
    )
    goal_b = r.get_json()["id"]

    client.post(
        f"/savings-goals/{goal_a}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )
    client.post(
        f"/savings-goals/{goal_b}/contribute",
        json={"amount": 1000},
        headers=auth_header,
    )

    r = client.get("/savings-goals/summary", headers=auth_header)
    assert r.status_code == 200
    summary = r.get_json()
    assert summary["active_goals"] == 2
    assert summary["total_target"] == 3000
    assert summary["total_saved"] == 1500
    assert summary["overall_progress"] == 50.0


def test_goal_defaults_to_user_preferred_currency(client, auth_header):
    """Test that goals default to user's preferred currency."""
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/savings-goals",
        json={"name": "Euro Fund", "target_amount": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["currency"] == "EUR"


def test_custom_milestones(client, auth_header):
    """Test creating goals with custom milestones."""
    payload = {
        "name": "Custom Goal",
        "target_amount": 10000,
        "milestones": [
            {"title": "First $1K", "target_percentage": 10},
            {"title": "Quarter Way", "target_percentage": 25},
            {"title": "Halfway!", "target_percentage": 50},
            {"title": "Done!", "target_percentage": 100},
        ],
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    milestones = r.get_json()["milestones"]
    assert len(milestones) == 4
    assert milestones[0]["title"] == "First $1K"
    assert milestones[0]["target_percentage"] == 10


def test_filter_by_status(client, auth_header):
    """Test filtering goals by status."""
    # Create active and cancelled goals
    r = client.post(
        "/savings-goals",
        json={"name": "Active Goal", "target_amount": 1000},
        headers=auth_header,
    )
    active_id = r.get_json()["id"]

    r = client.post(
        "/savings-goals",
        json={"name": "Cancelled Goal", "target_amount": 2000},
        headers=auth_header,
    )
    cancelled_id = r.get_json()["id"]
    client.patch(
        f"/savings-goals/{cancelled_id}",
        json={"status": "CANCELLED"},
        headers=auth_header,
    )

    # Default shows only active
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == active_id

    # Show all
    r = client.get("/savings-goals?status=ALL", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2

    # Show only cancelled
    r = client.get("/savings-goals?status=CANCELLED", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == cancelled_id
