"""Comprehensive tests for savings goals feature."""
from decimal import Decimal

import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
from app.models_savings import SavingsGoal, SavingsMilestone, GoalStatus


# ── helpers ──────────────────────────────────────────────────

def _create_goal(client, headers, name="Vacation", target=1000.0):
    return client.post(
        "/savings",
        json={"name": name, "target_amount": target},
        headers=headers,
    )


# ── CRUD tests ───────────────────────────────────────────────


def test_create_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Vacation"
    assert data["target_amount"] == 1000.0
    assert data["current_amount"] == 0.0
    assert data["remaining"] == 1000.0
    assert data["progress_pct"] == 0.0
    assert data["status"] == "active"
    assert data["currency"] == "INR"
    assert len(data["milestones"]) == 4


def test_create_goal_validation(client, auth_header):
    # Missing name
    r = client.post("/savings", json={"target_amount": 100}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]

    # Empty name
    r = client.post("/savings", json={"name": "  ", "target_amount": 100}, headers=auth_header)
    assert r.status_code == 400

    # Missing target
    r = client.post("/savings", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 400
    assert "target_amount" in r.get_json()["error"]

    # Zero target
    r = client.post("/savings", json={"name": "Test", "target_amount": 0}, headers=auth_header)
    assert r.status_code == 400

    # Negative target
    r = client.post("/savings", json={"name": "Test", "target_amount": -50}, headers=auth_header)
    assert r.status_code == 400

    # Invalid deadline
    r = client.post(
        "/savings",
        json={"name": "Test", "target_amount": 100, "deadline": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_list_goals_empty(client, auth_header):
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_goals_with_data(client, auth_header):
    _create_goal(client, auth_header, "Goal A", 500)
    _create_goal(client, auth_header, "Goal B", 1000)
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 2
    names = {g["name"] for g in items}
    assert names == {"Goal A", "Goal B"}


def test_get_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    gid = r.get_json()["id"]
    r = client.get(f"/savings/{gid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == gid


def test_get_goal_not_found(client, auth_header):
    r = client.get("/savings/9999", headers=auth_header)
    assert r.status_code == 404


def test_update_goal(client, auth_header):
    r = _create_goal(client, auth_header, "Old Name", 500)
    gid = r.get_json()["id"]
    r = client.patch(
        f"/savings/{gid}",
        json={"name": "New Name", "target_amount": 800},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "New Name"
    assert data["target_amount"] == 800.0


def test_update_goal_deadline(client, auth_header):
    r = _create_goal(client, auth_header)
    gid = r.get_json()["id"]
    r = client.patch(
        f"/savings/{gid}",
        json={"deadline": "2026-12-31"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["deadline"] == "2026-12-31"


def test_update_goal_clear_deadline(client, auth_header):
    r = _create_goal(client, auth_header)
    gid = r.get_json()["id"]
    client.patch(f"/savings/{gid}", json={"deadline": "2026-12-31"}, headers=auth_header)
    r = client.patch(f"/savings/{gid}", json={"deadline": None}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["deadline"] is None


def test_delete_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    gid = r.get_json()["id"]
    r = client.delete(f"/savings/{gid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"
    r = client.get(f"/savings/{gid}", headers=auth_header)
    assert r.status_code == 404


def test_delete_goal_not_found(client, auth_header):
    r = client.delete("/savings/9999", headers=auth_header)
    assert r.status_code == 404


# ── Contribution tests ───────────────────────────────────────


def test_contribute(client, auth_header):
    r = _create_goal(client, auth_header, "Trip", 1000)
    gid = r.get_json()["id"]
    r = client.post(
        f"/savings/{gid}/contribute",
        json={"amount": 250, "notes": "First deposit"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["amount"] == 250.0
    assert data["notes"] == "First deposit"
    assert data["goal_id"] == gid

    # Verify goal updated
    r = client.get(f"/savings/{gid}", headers=auth_header)
    goal = r.get_json()
    assert goal["current_amount"] == 250.0
    assert goal["remaining"] == 750.0
    assert goal["progress_pct"] == 25.0


def test_contribute_milestone_reached(client, auth_header):
    r = _create_goal(client, auth_header, "House", 2000)
    gid = r.get_json()["id"]
    # Contribute 50% -> should reach 25% and 50% milestones
    r = client.post(
        f"/savings/{gid}/contribute",
        json={"amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert sorted(data["new_milestones"]) == [25, 50]
    assert data["completed"] is False


def test_contribute_goal_completed(client, auth_header):
    r = _create_goal(client, auth_header, "Laptop", 500)
    gid = r.get_json()["id"]
    r = client.post(
        f"/savings/{gid}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["completed"] is True
    # All milestones reached
    assert sorted(data["new_milestones"]) == [25, 50, 75, 100]

    # Verify status
    r = client.get(f"/savings/{gid}", headers=auth_header)
    assert r.get_json()["status"] == "completed"


def test_contribute_validation(client, auth_header):
    r = _create_goal(client, auth_header)
    gid = r.get_json()["id"]

    # Zero amount
    r = client.post(
        f"/savings/{gid}/contribute",
        json={"amount": 0},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Negative amount
    r = client.post(
        f"/savings/{gid}/contribute",
        json={"amount": -10},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_contribute_goal_not_found(client, auth_header):
    r = client.post(
        "/savings/9999/contribute",
        json={"amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_contribute_to_completed_returns_error(client, auth_header):
    r = _create_goal(client, auth_header, "Done", 100)
    gid = r.get_json()["id"]
    client.post(f"/savings/{gid}/contribute", json={"amount": 100}, headers=auth_header)
    r = client.post(
        f"/savings/{gid}/contribute",
        json={"amount": 50},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "completed" in r.get_json()["error"]


# ── Summary tests ────────────────────────────────────────────


def test_summary_empty(client, auth_header):
    r = client.get("/savings/summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_goals"] == 0
    assert data["active"] == 0
    assert data["completed"] == 0
    assert data["abandoned"] == 0
    assert data["total_target"] == 0
    assert data["total_saved"] == 0
    assert data["overall_progress_pct"] == 0


def test_summary_with_goals(client, auth_header):
    # Create two goals, contribute to one
    r = _create_goal(client, auth_header, "Goal1", 1000)
    gid1 = r.get_json()["id"]
    _create_goal(client, auth_header, "Goal2", 500)
    client.post(f"/savings/{gid1}/contribute", json={"amount": 250}, headers=auth_header)

    r = client.get("/savings/summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_goals"] == 2
    assert data["active"] == 2
    assert data["total_target"] == 1500.0
    assert data["total_saved"] == 250.0
    assert data["overall_progress_pct"] > 0


# ── Edge cases ───────────────────────────────────────────────


def test_progress_pct_calculation(app_fixture):
    """Unit test for progress calculation logic."""
    with app_fixture.app_context():
        goal = SavingsGoal(
            user_id=1,
            name="Test",
            target_amount=Decimal("400.00"),
            current_amount=Decimal("100.00"),
        )
        # 100/400 = 25%
        pct = round(float(goal.current_amount) / float(goal.target_amount) * 100, 2)
        assert pct == 25.0


def test_remaining_calculation(app_fixture):
    """Unit test for remaining calculation logic."""
    with app_fixture.app_context():
        goal = SavingsGoal(
            user_id=1,
            name="Test",
            target_amount=Decimal("500.00"),
            current_amount=Decimal("150.00"),
        )
        remaining = float(goal.target_amount) - float(goal.current_amount)
        assert remaining == 350.0


def test_abandon_goal(client, auth_header):
    r = _create_goal(client, auth_header, "Old Goal", 200)
    gid = r.get_json()["id"]
    r = client.post(f"/savings/{gid}/abandon", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["status"] == "abandoned"


def test_abandon_goal_not_found(client, auth_header):
    r = client.post("/savings/9999/abandon", headers=auth_header)
    assert r.status_code == 404


def test_cannot_contribute_to_abandoned(client, auth_header):
    r = _create_goal(client, auth_header, "Abandoned", 500)
    gid = r.get_json()["id"]
    client.post(f"/savings/{gid}/abandon", headers=auth_header)
    r = client.post(
        f"/savings/{gid}/contribute",
        json={"amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "abandoned" in r.get_json()["error"]


def test_cannot_update_abandoned_goal(client, auth_header):
    r = _create_goal(client, auth_header, "Frozen", 300)
    gid = r.get_json()["id"]
    client.post(f"/savings/{gid}/abandon", headers=auth_header)
    r = client.patch(
        f"/savings/{gid}",
        json={"name": "Nope"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "abandoned" in r.get_json()["error"]


def test_cannot_abandon_completed_goal(client, auth_header):
    r = _create_goal(client, auth_header, "Finished", 100)
    gid = r.get_json()["id"]
    client.post(f"/savings/{gid}/contribute", json={"amount": 100}, headers=auth_header)
    r = client.post(f"/savings/{gid}/abandon", headers=auth_header)
    assert r.status_code == 400
    assert "completed" in r.get_json()["error"]


def test_milestone_auto_creation(app_fixture):
    """Verify default milestones are created with each goal."""
    with app_fixture.app_context():
        from app.services.savings import SavingsService

        svc = SavingsService()
        # We need a user first
        from app.models import User
        u = User(email="ms@test.com", password_hash="x")
        db.session.add(u)
        db.session.flush()

        goal, err = svc.create_goal(u.id, {"name": "Car", "target_amount": 5000})
        assert err is None
        milestones = goal.milestones.order_by(SavingsMilestone.percentage).all()
        pcts = [m.percentage for m in milestones]
        assert pcts == [25, 50, 75, 100]
        assert all(not m.reached for m in milestones)


def test_goal_with_deadline(client, auth_header):
    r = client.post(
        "/savings",
        json={"name": "Wedding", "target_amount": 5000, "deadline": "2027-06-15"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["deadline"] == "2027-06-15"


def test_goal_custom_currency(client, auth_header):
    r = client.post(
        "/savings",
        json={"name": "Euro Trip", "target_amount": 2000, "currency": "EUR"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


def test_multiple_contributions_accumulate(client, auth_header):
    r = _create_goal(client, auth_header, "Accumulate", 1000)
    gid = r.get_json()["id"]
    client.post(f"/savings/{gid}/contribute", json={"amount": 100}, headers=auth_header)
    client.post(f"/savings/{gid}/contribute", json={"amount": 200}, headers=auth_header)
    client.post(f"/savings/{gid}/contribute", json={"amount": 300}, headers=auth_header)

    r = client.get(f"/savings/{gid}", headers=auth_header)
    goal = r.get_json()
    assert goal["current_amount"] == 600.0
    assert goal["remaining"] == 400.0
    assert goal["progress_pct"] == 60.0


def test_update_not_found(client, auth_header):
    r = client.patch("/savings/9999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404


def test_auth_required(client):
    """All savings endpoints require authentication."""
    r = client.get("/savings")
    assert r.status_code == 401
    r = client.post("/savings", json={"name": "X", "target_amount": 100})
    assert r.status_code == 401
