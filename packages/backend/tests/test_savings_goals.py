"""Tests for savings goals and milestones feature."""
from datetime import date, timedelta


def test_list_goals_empty(client, auth_header):
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_goal_with_defaults(client, auth_header):
    payload = {
        "name": "Emergency Fund",
        "target_amount": 10000.00,
        "currency": "USD",
        "target_date": (date.today() + timedelta(days=365)).isoformat(),
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 10000.00
    assert data["current_amount"] == 0.0
    assert data["progress_pct"] == 0.0
    assert data["status"] == "ACTIVE"
    # Default milestones: 25%, 50%, 75%, 100%
    assert len(data["milestones"]) == 4
    percentages = [m["target_percentage"] for m in data["milestones"]]
    assert percentages == [25, 50, 75, 100]
    for m in data["milestones"]:
        assert m["reached"] is False


def test_create_goal_custom_milestones(client, auth_header):
    payload = {
        "name": "Vacation",
        "target_amount": 5000.00,
        "milestones": [
            {"name": "Booked flights", "target_percentage": 30},
            {"name": "Hotel paid", "target_percentage": 70},
            {"name": "All set", "target_percentage": 100},
        ],
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert len(data["milestones"]) == 3
    assert data["milestones"][0]["target_percentage"] == 30


def test_create_goal_validation(client, auth_header):
    # Missing name
    r = client.post(
        "/savings-goals", json={"target_amount": 100}, headers=auth_header
    )
    assert r.status_code == 400

    # Missing target_amount
    r = client.post(
        "/savings-goals", json={"name": "Test"}, headers=auth_header
    )
    assert r.status_code == 400

    # Negative target_amount
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_get_goal(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "House", "target_amount": 50000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "House"


def test_get_goal_not_found(client, auth_header):
    r = client.get("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_goal(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "Car", "target_amount": 20000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.patch(
        f"/savings-goals/{goal_id}",
        json={"name": "New Car", "target_amount": 25000},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "New Car"
    assert r.get_json()["target_amount"] == 25000.0


def test_delete_goal(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "Temp", "target_amount": 100},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.delete(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "cancelled"

    # Verify status is CANCELLED
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.get_json()["status"] == "CANCELLED"


def test_contribute_and_milestones(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "Fund", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Contribute 250 -> 25% milestone reached
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 250},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["current_amount"] == 250.0
    assert data["progress_pct"] == 25.0
    reached_names = [m["name"] for m in data["newly_reached_milestones"]]
    assert "Getting Started" in reached_names

    # Contribute 500 more -> 75% (50% and 75% milestones)
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )
    data = r.get_json()
    assert data["current_amount"] == 750.0
    assert len(data["newly_reached_milestones"]) == 2

    # Contribute 250 more -> 100% goal completed
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 250},
        headers=auth_header,
    )
    data = r.get_json()
    assert data["status"] == "COMPLETED"
    assert data["progress_pct"] == 100.0


def test_contribute_validation(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "Fund", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Zero amount
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 0},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Negative amount
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_withdraw(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "Fund", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Add money first
    client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )

    # Withdraw some
    r = client.post(
        f"/savings-goals/{goal_id}/withdraw",
        json={"amount": 200},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["current_amount"] == 300.0

    # Try to withdraw more than available
    r = client.post(
        f"/savings-goals/{goal_id}/withdraw",
        json={"amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 404  # insufficient funds


def test_filter_by_status(client, auth_header):
    # Create two goals
    client.post(
        "/savings-goals",
        json={"name": "Active Goal", "target_amount": 1000},
        headers=auth_header,
    )
    r = client.post(
        "/savings-goals",
        json={"name": "To Cancel", "target_amount": 500},
        headers=auth_header,
    )
    cancel_id = r.get_json()["id"]
    client.delete(f"/savings-goals/{cancel_id}", headers=auth_header)

    # Filter active only
    r = client.get("/savings-goals?status=ACTIVE", headers=auth_header)
    goals = r.get_json()
    assert all(g["status"] == "ACTIVE" for g in goals)

    # Filter cancelled
    r = client.get("/savings-goals?status=CANCELLED", headers=auth_header)
    goals = r.get_json()
    assert all(g["status"] == "CANCELLED" for g in goals)
    assert len(goals) == 1


def test_goal_defaults_to_user_currency(client, auth_header):
    # Set user preferred currency
    client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    r = client.post(
        "/savings-goals",
        json={"name": "Euro Fund", "target_amount": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


def test_cannot_contribute_to_cancelled_goal(client, auth_header):
    r = client.post(
        "/savings-goals",
        json={"name": "Cancelled", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]
    client.delete(f"/savings-goals/{goal_id}", headers=auth_header)

    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_days_remaining(client, auth_header):
    future = (date.today() + timedelta(days=30)).isoformat()
    r = client.post(
        "/savings-goals",
        json={"name": "Short Goal", "target_amount": 500, "target_date": future},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["days_remaining"] is not None
    assert data["days_remaining"] <= 30
