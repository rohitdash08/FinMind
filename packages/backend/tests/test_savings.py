from datetime import date, timedelta


def test_savings_goals_crud(client, auth_header):
    """Full CRUD lifecycle for savings goals."""
    # Initially empty
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create a savings goal
    payload = {
        "name": "Emergency Fund",
        "description": "6 months of expenses",
        "target_amount": 10000.00,
        "currency": "USD",
        "target_date": (date.today() + timedelta(days=365)).isoformat(),
        "icon": "shield",
        "color": "#22c55e",
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    goal_id = goal["id"]
    assert goal["name"] == "Emergency Fund"
    assert goal["target_amount"] == 10000.00
    assert goal["current_amount"] == 0
    assert goal["progress_pct"] == 0
    assert goal["status"] == "ACTIVE"
    assert goal["remaining"] == 10000.00

    # List goals — should have 1
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == goal_id

    # Get single goal
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert detail["name"] == "Emergency Fund"
    assert "contributions" in detail
    assert detail["contributions"] == []

    # Update goal
    r = client.patch(
        f"/savings/{goal_id}",
        json={"name": "Emergency Savings", "target_amount": 15000},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Emergency Savings"
    assert updated["target_amount"] == 15000.0

    # Delete goal
    r = client.delete(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # Verify deleted
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_savings_contributions(client, auth_header):
    """Test adding contributions and progress tracking."""
    # Create a goal
    payload = {
        "name": "Vacation Fund",
        "target_amount": 5000.00,
        "target_date": (date.today() + timedelta(days=180)).isoformat(),
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Add contribution
    r = client.post(
        f"/savings/{goal_id}/contributions",
        json={"amount": 1000, "note": "First deposit"},
        headers=auth_header,
    )
    assert r.status_code == 201
    result = r.get_json()
    assert result["contribution"]["amount"] == 1000
    assert result["contribution"]["note"] == "First deposit"
    assert result["goal"]["current_amount"] == 1000
    assert result["goal"]["progress_pct"] == 20.0
    assert result["goal"]["remaining"] == 4000.0

    # Add another contribution
    r = client.post(
        f"/savings/{goal_id}/contributions",
        json={"amount": 500, "note": "Second deposit"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["goal"]["current_amount"] == 1500
    assert r.get_json()["goal"]["progress_pct"] == 30.0

    # Get goal detail — should have 2 contributions
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert len(detail["contributions"]) == 2
    assert detail["current_amount"] == 1500


def test_savings_auto_complete(client, auth_header):
    """Goal should auto-complete when target is reached."""
    payload = {
        "name": "New Laptop",
        "target_amount": 2000.00,
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Add contribution that reaches target
    r = client.post(
        f"/savings/{goal_id}/contributions",
        json={"amount": 2000},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["goal"]["status"] == "COMPLETED"
    assert r.get_json()["goal"]["progress_pct"] == 100


def test_savings_withdraw(client, auth_header):
    """Test withdrawing from a savings goal."""
    payload = {
        "name": "Car Fund",
        "target_amount": 20000.00,
        "current_amount": 5000.00,
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Withdraw
    r = client.post(
        f"/savings/{goal_id}/withdraw",
        json={"amount": 1000, "note": "Emergency withdrawal"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["goal"]["current_amount"] == 4000

    # Over-withdraw should fail
    r = client.post(
        f"/savings/{goal_id}/withdraw",
        json={"amount": 50000},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "insufficient" in r.get_json()["error"]


def test_savings_summary(client, auth_header):
    """Test the summary endpoint."""
    # Create two goals
    client.post(
        "/savings",
        json={"name": "Goal 1", "target_amount": 1000, "current_amount": 500},
        headers=auth_header,
    )
    client.post(
        "/savings",
        json={"name": "Goal 2", "target_amount": 2000, "current_amount": 300},
        headers=auth_header,
    )

    r = client.get("/savings/summary", headers=auth_header)
    assert r.status_code == 200
    summary = r.get_json()
    assert summary["total_goals"] == 2
    assert summary["active_goals"] == 2
    assert summary["completed_goals"] == 0
    assert summary["total_saved"] == 800
    assert summary["total_target"] == 3000


def test_savings_validation(client, auth_header):
    """Test input validation."""
    # Missing required fields
    r = client.post("/savings", json={}, headers=auth_header)
    assert r.status_code == 400

    # Negative target_amount
    r = client.post(
        "/savings",
        json={"name": "Bad Goal", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Contribution to non-existent goal
    r = client.post(
        "/savings/99999/contributions",
        json={"amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_savings_status_filter(client, auth_header):
    """Test filtering goals by status."""
    # Create a goal and complete it
    r = client.post(
        "/savings",
        json={"name": "Small Goal", "target_amount": 100},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]
    client.post(
        f"/savings/{goal_id}/contributions",
        json={"amount": 100},
        headers=auth_header,
    )

    # Create an active goal
    client.post(
        "/savings",
        json={"name": "Active Goal", "target_amount": 5000},
        headers=auth_header,
    )

    # Filter active only
    r = client.get("/savings?status=ACTIVE", headers=auth_header)
    assert r.status_code == 200
    active = r.get_json()
    assert len(active) == 1
    assert active[0]["name"] == "Active Goal"

    # Filter completed only
    r = client.get("/savings?status=COMPLETED", headers=auth_header)
    assert r.status_code == 200
    completed = r.get_json()
    assert len(completed) == 1
    assert completed[0]["name"] == "Small Goal"

    # All
    r = client.get("/savings?status=ALL", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2


def test_savings_goal_defaults_to_user_currency(client, auth_header):
    """Goal should use user's preferred currency if not specified."""
    # Set user currency
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    # Create goal without specifying currency
    r = client.post(
        "/savings",
        json={"name": "Euro Goal", "target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"
