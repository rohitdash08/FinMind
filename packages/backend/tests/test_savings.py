"""Tests for savings goals API (bounty #133)."""

from datetime import date, timedelta


def test_savings_create_goal(client, auth_header):
    """Test creating a savings goal."""
    payload = {
        "name": "Emergency Fund",
        "target_amount": 10000,
        "currency": "USD",
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    assert goal["name"] == "Emergency Fund"
    assert float(goal["target_amount"]) == 10000.0
    assert goal["status"] == "active"


def test_savings_create_goal_with_deadline(client, auth_header):
    """Test creating a goal with a deadline."""
    future = (date.today() + timedelta(days=365)).isoformat()
    payload = {
        "name": "Vacation Fund",
        "target_amount": 5000,
        "deadline": future,
    }
    r = client.post("/savings", json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    assert goal["deadline"] is not None


def test_savings_create_goal_validation(client, auth_header):
    """Test goal creation validation."""
    r = client.post("/savings", json={"target_amount": 1000}, headers=auth_header)
    assert r.status_code == 400

    r = client.post(
        "/savings",
        json={"name": "Test", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_savings_list_goals(client, auth_header):
    """Test listing savings goals."""
    for i in range(3):
        r = client.post(
            "/savings",
            json={"name": f"Goal {i}", "target_amount": 1000 * (i + 1)},
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 3


def test_savings_get_goal(client, auth_header):
    """Test getting a single goal with progress."""
    r = client.post(
        "/savings",
        json={"name": "Test Goal", "target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    goal = r.get_json()
    assert goal["id"] == goal_id
    assert "progress" in goal


def test_savings_get_not_found(client, auth_header):
    """Test getting non-existent goal returns 404."""
    r = client.get("/savings/99999", headers=auth_header)
    assert r.status_code == 404


def test_savings_add_contribution(client, auth_header):
    """Test adding a contribution to a goal."""
    r = client.post(
        "/savings",
        json={"name": "Save Up", "target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/{goal_id}/contributions",
        json={"amount": 250, "notes": "First deposit"},
        headers=auth_header,
    )
    assert r.status_code == 201
    contrib = r.get_json()
    assert float(contrib["amount"]) == 250.0


def test_savings_contribution_invalid_amount(client, auth_header):
    """Test contribution with invalid amount."""
    r = client.post(
        "/savings",
        json={"name": "Test", "target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/savings/{goal_id}/contributions",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_savings_list_milestones(client, auth_header):
    """Test listing auto-created milestones."""
    r = client.post(
        "/savings",
        json={"name": "Milestone Test", "target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings/{goal_id}/milestones", headers=auth_header)
    assert r.status_code == 200
    milestones = r.get_json()
    assert len(milestones) == 4  # 25%, 50%, 75%, 100%


def test_savings_list_contributions(client, auth_header):
    """Test listing contributions for a goal."""
    r = client.post(
        "/savings",
        json={"name": "Contrib Test", "target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    for amt in [100, 200]:
        r = client.post(
            f"/savings/{goal_id}/contributions",
            json={"amount": amt},
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get(f"/savings/{goal_id}/contributions", headers=auth_header)
    assert r.status_code == 200
    contribs = r.get_json()
    assert len(contribs) == 2


def test_savings_delete_goal(client, auth_header):
    """Test deleting a goal."""
    r = client.post(
        "/savings",
        json={"name": "Delete Me", "target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.delete(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 404


def test_savings_abandon_goal(client, auth_header):
    """Test abandoning a goal."""
    r = client.post(
        "/savings",
        json={"name": "Abandon Me", "target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    goal_id = r.get_json()["id"]

    r = client.post(f"/savings/{goal_id}/abandon", headers=auth_header)
    assert r.status_code == 200
    goal = r.get_json()
    assert goal["status"] == "abandoned"
