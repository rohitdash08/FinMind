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
        "deadline": (date.today() + timedelta(days=365)).isoformat(),
        "category": "EMERGENCY",
    }
    r = client.post("/savings-goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    goal_id = goal["id"]
    assert goal["name"] == "Emergency Fund"
    assert goal["target_amount"] == 10000.0
    assert goal["current_amount"] == 0.0
    assert goal["category"] == "EMERGENCY"
    assert goal["progress_pct"] == 0.0
    # Should have 4 milestones auto-generated
    assert len(goal["milestones"]) == 4
    assert [m["percentage"] for m in goal["milestones"]] == [25, 50, 75, 100]
    assert all(not m["reached"] for m in goal["milestones"])

    # List has 1
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == goal_id

    # Get single goal
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert detail["name"] == "Emergency Fund"
    assert "contributions" in detail
    assert detail["days_remaining"] is not None

    # Update goal
    r = client.put(
        f"/savings-goals/{goal_id}",
        json={"name": "Rainy Day Fund", "target_amount": 15000},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Rainy Day Fund"
    assert r.get_json()["target_amount"] == 15000.0

    # Delete goal
    r = client.delete(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # Verify deleted
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 404


def test_contribute_and_milestones(client, auth_header):
    """Test contributions and milestone tracking."""
    # Create goal with target of 1000
    r = client.post(
        "/savings-goals",
        json={"name": "Vacation", "target_amount": 1000, "category": "VACATION"},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    # Contribute 250 (hits 25% milestone)
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 250, "note": "March savings"},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["goal"]["current_amount"] == 250.0
    assert data["goal"]["progress_pct"] == 25.0
    assert len(data["newly_reached_milestones"]) == 1
    assert data["newly_reached_milestones"][0]["percentage"] == 25
    assert data["contribution"]["amount"] == 250.0
    assert data["contribution"]["note"] == "March savings"

    # Contribute 500 more (hits 50% and 75%)
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["goal"]["current_amount"] == 750.0
    assert data["goal"]["progress_pct"] == 75.0
    newly = data["newly_reached_milestones"]
    assert len(newly) == 2
    pcts = sorted([m["percentage"] for m in newly])
    assert pcts == [50, 75]

    # Check milestones endpoint
    r = client.get(f"/savings-goals/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    milestones = r.get_json()
    assert len(milestones) == 4
    reached = [m for m in milestones if m["reached"]]
    assert len(reached) == 3  # 25, 50, 75
    not_reached = [m for m in milestones if not m["reached"]]
    assert len(not_reached) == 1
    assert not_reached[0]["percentage"] == 100

    # Contribute remaining 250 (hits 100%)
    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": 250},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["goal"]["progress_pct"] == 100.0
    assert len(data["newly_reached_milestones"]) == 1
    assert data["newly_reached_milestones"][0]["percentage"] == 100


def test_validation_errors(client, auth_header):
    """Test input validation."""
    # Missing required fields
    r = client.post("/savings-goals", json={}, headers=auth_header)
    assert r.status_code == 400
    assert "name is required" in r.get_json()["error"]

    # Negative target amount
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "positive" in r.get_json()["error"]

    # Invalid category
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": 100, "category": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "category" in r.get_json()["error"]

    # Invalid contribution amount
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": 100},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "positive" in r.get_json()["error"]

    r = client.post(
        f"/savings-goals/{goal_id}/contribute",
        json={"amount": "not_a_number"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_goal_not_found(client, auth_header):
    """Test 404 for non-existent goals."""
    r = client.get("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404

    r = client.put("/savings-goals/99999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404

    r = client.post(
        "/savings-goals/99999/contribute",
        json={"amount": 10},
        headers=auth_header,
    )
    assert r.status_code == 404

    r = client.get("/savings-goals/99999/milestones", headers=auth_header)
    assert r.status_code == 404


def test_goal_with_initial_amount(client, auth_header):
    """Test creating a goal with initial current_amount."""
    r = client.post(
        "/savings-goals",
        json={"name": "Car Fund", "target_amount": 1000, "current_amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal = r.get_json()
    assert goal["current_amount"] == 500.0
    assert goal["progress_pct"] == 50.0
    # Milestones at 25% and 50% should be reached
    reached = [m for m in goal["milestones"] if m["reached"]]
    assert len(reached) == 2


def test_goal_defaults_to_user_currency(client, auth_header):
    """Test that goal defaults to user's preferred currency."""
    client.patch(
        "/auth/me", json={"preferred_currency": "USD"}, headers=auth_header
    )
    r = client.post(
        "/savings-goals",
        json={"name": "Test", "target_amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "USD"
