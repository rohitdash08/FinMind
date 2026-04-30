"""Tests for goal-based savings tracking & milestones (Issue #133)."""


def test_create_goal(client, auth_header):
    """Creating a savings goal should return 201 with auto-generated milestones."""
    payload = {
        "name": "Emergency Fund",
        "description": "6 months of expenses",
        "target_amount": 10000.00,
        "currency": "INR",
        "deadline": "2026-12-31",
        "color": "#10b981",
    }
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    assert goal["name"] == "Emergency Fund"
    assert goal["description"] == "6 months of expenses"
    assert goal["target_amount"] == 10000.00
    assert goal["current_amount"] == 0.00
    assert goal["progress"] == 0.0
    assert goal["currency"] == "INR"
    assert goal["deadline"] == "2026-12-31"
    assert goal["is_completed"] is False
    assert goal["color"] == "#10b981"
    assert "id" in goal


def test_create_goal_validation(client, auth_header):
    """Creating a goal without name or valid target_amount should fail."""
    # Missing name
    r = client.post(
        "/savings/goals",
        json={"target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "name" in r.get_json()["error"].lower()

    # Invalid target_amount
    r = client.post(
        "/savings/goals",
        json={"name": "Test", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Zero target_amount
    r = client.post(
        "/savings/goals",
        json={"name": "Test", "target_amount": 0},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_list_goals(client, auth_header):
    """Listing goals should return all user goals."""
    # Start empty
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create two goals
    client.post(
        "/savings/goals",
        json={"name": "Goal A", "target_amount": 5000},
        headers=auth_header,
    )
    client.post(
        "/savings/goals",
        json={"name": "Goal B", "target_amount": 10000},
        headers=auth_header,
    )

    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    goals = r.get_json()
    assert len(goals) == 2
    names = {g["name"] for g in goals}
    assert "Goal A" in names
    assert "Goal B" in names


def test_get_goal_detail(client, auth_header):
    """Getting a single goal should include milestones and contributions."""
    r = client.post(
        "/savings/goals",
        json={"name": "Detail Test", "target_amount": 8000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert detail["name"] == "Detail Test"
    assert "milestones" in detail
    assert len(detail["milestones"]) == 4  # 25%, 50%, 75%, 100%
    pcts = [m["target_percentage"] for m in detail["milestones"]]
    assert pcts == [25, 50, 75, 100]
    assert all(m["reached_at"] is None for m in detail["milestones"])
    assert "contributions" in detail
    assert detail["contributions"] == []


def test_get_goal_not_found(client, auth_header):
    """Accessing a non-existent goal returns 404."""
    r = client.get("/savings/goals/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_goal(client, auth_header):
    """Updating a goal should change its fields."""
    r = client.post(
        "/savings/goals",
        json={"name": "Old Name", "target_amount": 5000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.put(
        f"/savings/goals/{goal_id}",
        json={"name": "New Name", "description": "Updated desc", "target_amount": 7000},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "New Name"
    assert updated["description"] == "Updated desc"
    assert updated["target_amount"] == 7000.00


def test_update_goal_not_found(client, auth_header):
    """Updating a non-existent goal returns 404."""
    r = client.put(
        "/savings/goals/99999",
        json={"name": "Nope"},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_delete_goal(client, auth_header):
    """Deleting a goal should remove it."""
    r = client.post(
        "/savings/goals",
        json={"name": "To Delete", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    r = client.delete(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # Verify it's gone
    r = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 404


def test_delete_goal_not_found(client, auth_header):
    """Deleting a non-existent goal returns 404."""
    r = client.delete("/savings/goals/99999", headers=auth_header)
    assert r.status_code == 404


def test_add_contribution(client, auth_header):
    """Adding a contribution should update current_amount and progress."""
    r = client.post(
        "/savings/goals",
        json={"name": "Contrib Test", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Add first contribution
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 250, "note": "First deposit"},
        headers=auth_header,
    )
    assert r.status_code == 201
    detail = r.get_json()
    assert detail["current_amount"] == 250.00
    assert detail["progress"] == 25.0
    assert len(detail["contributions"]) == 1
    assert detail["contributions"][0]["amount"] == 250.00
    assert detail["contributions"][0]["note"] == "First deposit"


def test_contribution_validation(client, auth_header):
    """Adding invalid contribution amounts should fail."""
    r = client.post(
        "/savings/goals",
        json={"name": "Validation Test", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Zero amount
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 0},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Negative amount
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Missing amount
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"note": "No amount"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_contribution_not_found(client, auth_header):
    """Contributing to a non-existent goal returns 404."""
    r = client.post(
        "/savings/goals/99999/contribute",
        json={"amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_milestone_auto_check(client, auth_header):
    """Milestones should be automatically marked when thresholds are crossed."""
    r = client.post(
        "/savings/goals",
        json={"name": "Milestone Test", "target_amount": 1000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Contribute 250 -> should reach 25% milestone
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 250},
        headers=auth_header,
    )
    assert r.status_code == 201
    detail = r.get_json()
    ms_25 = next(m for m in detail["milestones"] if m["target_percentage"] == 25)
    assert ms_25["reached_at"] is not None
    ms_50 = next(m for m in detail["milestones"] if m["target_percentage"] == 50)
    assert ms_50["reached_at"] is None

    # Contribute 250 more -> should reach 50%
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 250},
        headers=auth_header,
    )
    detail = r.get_json()
    ms_50 = next(m for m in detail["milestones"] if m["target_percentage"] == 50)
    assert ms_50["reached_at"] is not None
    ms_75 = next(m for m in detail["milestones"] if m["target_percentage"] == 75)
    assert ms_75["reached_at"] is None

    # Contribute 500 more -> should reach 75% and 100%, and goal should be completed
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )
    detail = r.get_json()
    assert detail["current_amount"] == 1000.00
    assert detail["is_completed"] is True
    ms_75 = next(m for m in detail["milestones"] if m["target_percentage"] == 75)
    assert ms_75["reached_at"] is not None
    ms_100 = next(m for m in detail["milestones"] if m["target_percentage"] == 100)
    assert ms_100["reached_at"] is not None


def test_overshoot_contribution(client, auth_header):
    """Contributing more than the remaining amount should still work and complete the goal."""
    r = client.post(
        "/savings/goals",
        json={"name": "Overshoot Test", "target_amount": 500},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Contribute 1000 (more than target of 500)
    r = client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    detail = r.get_json()
    assert detail["current_amount"] == 1000.00
    assert detail["is_completed"] is True
    assert detail["progress"] == 200.0  # Over 100%
    # All milestones should be reached
    assert all(m["reached_at"] is not None for m in detail["milestones"])


def test_savings_summary(client, auth_header):
    """Summary endpoint should aggregate all user goals."""
    # Start with empty summary
    r = client.get("/savings/summary", headers=auth_header)
    assert r.status_code == 200
    s = r.get_json()
    assert s["total_goals"] == 0
    assert s["total_saved"] == 0
    assert s["overall_progress"] == 0

    # Create two goals
    r = client.post(
        "/savings/goals",
        json={"name": "Fund A", "target_amount": 1000},
        headers=auth_header,
    )
    goal_a_id = r.get_json()["id"]

    r = client.post(
        "/savings/goals",
        json={"name": "Fund B", "target_amount": 2000},
        headers=auth_header,
    )
    goal_b_id = r.get_json()["id"]

    # Add contributions
    client.post(
        f"/savings/goals/{goal_a_id}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )
    client.post(
        f"/savings/goals/{goal_b_id}/contribute",
        json={"amount": 1000},
        headers=auth_header,
    )

    r = client.get("/savings/summary", headers=auth_header)
    assert r.status_code == 200
    s = r.get_json()
    assert s["total_goals"] == 2
    assert s["completed_goals"] == 0
    assert s["in_progress_goals"] == 2
    assert s["total_target"] == 3000.0
    assert s["total_saved"] == 1500.0
    assert s["overall_progress"] == 50.0


def test_savings_summary_with_completed(client, auth_header):
    """Summary should accurately count completed goals."""
    r = client.post(
        "/savings/goals",
        json={"name": "Quick Goal", "target_amount": 100},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    # Complete it
    client.post(
        f"/savings/goals/{goal_id}/contribute",
        json={"amount": 100},
        headers=auth_header,
    )

    r = client.get("/savings/summary", headers=auth_header)
    assert r.status_code == 200
    s = r.get_json()
    assert s["completed_goals"] == 1
    assert s["in_progress_goals"] == 0


def test_savings_requires_auth(client):
    """All savings endpoints should require JWT authentication."""
    endpoints = [
        ("GET", "/savings/goals"),
        ("POST", "/savings/goals"),
        ("GET", "/savings/goals/1"),
        ("PUT", "/savings/goals/1"),
        ("DELETE", "/savings/goals/1"),
        ("POST", "/savings/goals/1/contribute"),
        ("GET", "/savings/summary"),
    ]
    for method, path in endpoints:
        r = getattr(client, method.lower())(path)
        assert r.status_code in (401, 422), f"{method} {path} should require auth"


def test_multiple_contributions(client, auth_header):
    """Multiple contributions should be tracked and ordered by date desc."""
    r = client.post(
        "/savings/goals",
        json={"name": "Multi Contrib", "target_amount": 5000},
        headers=auth_header,
    )
    goal_id = r.get_json()["id"]

    for i in range(5):
        client.post(
            f"/savings/goals/{goal_id}/contribute",
            json={"amount": 100, "note": f"Payment {i+1}"},
            headers=auth_header,
        )

    r = client.get(f"/savings/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert detail["current_amount"] == 500.00
    assert len(detail["contributions"]) == 5
    # Most recent should be first
    assert detail["contributions"][0]["note"] == "Payment 5"
