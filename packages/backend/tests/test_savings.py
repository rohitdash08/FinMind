"""Tests for savings goal tracking (issue #133)."""
from datetime import date, timedelta
from decimal import Decimal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_goal(client, auth_header, name="Emergency Fund", target=1000, target_date=None):
    payload = {"name": name, "target_amount": target}
    if target_date:
        payload["target_date"] = target_date
    r = client.post("/savings/goals", json=payload, headers=auth_header)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _deposit(client, auth_header, goal_id, amount, note=None):
    payload = {"amount": amount}
    if note:
        payload["note"] = note
    r = client.post(f"/savings/goals/{goal_id}/deposit", json=payload, headers=auth_header)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ---------------------------------------------------------------------------
# Auth gates
# ---------------------------------------------------------------------------

def test_list_goals_requires_auth(client):
    r = client.get("/savings/goals")
    assert r.status_code == 401


def test_create_goal_requires_auth(client):
    r = client.post("/savings/goals", json={"name": "x", "target_amount": 100})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_goal_returns_201(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Holiday Fund", "target_amount": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Holiday Fund"
    assert data["target_amount"] == 5000
    assert data["current_amount"] == 0
    assert data["progress_pct"] == 0.0
    assert data["status"] == "ACTIVE"


def test_create_goal_with_target_date(client, auth_header):
    future = (date.today() + timedelta(days=90)).isoformat()
    r = client.post(
        "/savings/goals",
        json={"name": "Laptop", "target_amount": 2000, "target_date": future},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["target_date"] == future


def test_create_goal_missing_name_returns_400(client, auth_header):
    r = client.post("/savings/goals", json={"target_amount": 100}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json().get("error", "").lower()


def test_create_goal_invalid_amount_returns_400(client, auth_header):
    r = client.post(
        "/savings/goals", json={"name": "Bad", "target_amount": -50}, headers=auth_header
    )
    assert r.status_code == 400


def test_create_goal_invalid_date_returns_400(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Bad Date", "target_amount": 100, "target_date": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# List / Get
# ---------------------------------------------------------------------------

def test_list_goals_empty(client, auth_header):
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_goals_returns_own_goals(client, auth_header):
    _create_goal(client, auth_header, "A", 100)
    _create_goal(client, auth_header, "B", 200)
    r = client.get("/savings/goals", headers=auth_header)
    names = {g["name"] for g in r.get_json()}
    assert "A" in names and "B" in names


def test_get_goal_404_for_missing(client, auth_header):
    r = client.get("/savings/goals/99999", headers=auth_header)
    assert r.status_code == 404


def test_get_goal_returns_goal(client, auth_header):
    goal = _create_goal(client, auth_header, "Savings Pot", 3000)
    r = client.get(f"/savings/goals/{goal['id']}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Savings Pot"


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def test_update_goal_name(client, auth_header):
    goal = _create_goal(client, auth_header, "Old Name", 500)
    r = client.patch(
        f"/savings/goals/{goal['id']}",
        json={"name": "New Name"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "New Name"


def test_update_goal_status_abandon(client, auth_header):
    goal = _create_goal(client, auth_header, "Trip", 5000)
    r = client.patch(
        f"/savings/goals/{goal['id']}",
        json={"status": "ABANDONED"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "ABANDONED"


def test_update_goal_invalid_status(client, auth_header):
    goal = _create_goal(client, auth_header, "Trip", 5000)
    r = client.patch(
        f"/savings/goals/{goal['id']}",
        json={"status": "FLYING"},
        headers=auth_header,
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_goal(client, auth_header):
    goal = _create_goal(client, auth_header, "To Delete", 100)
    r = client.delete(f"/savings/goals/{goal['id']}", headers=auth_header)
    assert r.status_code == 204
    r2 = client.get(f"/savings/goals/{goal['id']}", headers=auth_header)
    assert r2.status_code == 404


def test_delete_nonexistent_goal(client, auth_header):
    r = client.delete("/savings/goals/99999", headers=auth_header)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Deposits
# ---------------------------------------------------------------------------

def test_deposit_increases_balance(client, auth_header):
    goal = _create_goal(client, auth_header, "House", 10000)
    updated = _deposit(client, auth_header, goal["id"], 2500)
    assert updated["current_amount"] == 2500
    assert updated["progress_pct"] == 25.0


def test_deposit_invalid_amount(client, auth_header):
    goal = _create_goal(client, auth_header, "Car", 5000)
    r = client.post(
        f"/savings/goals/{goal['id']}/deposit",
        json={"amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_deposit_completes_goal(client, auth_header):
    goal = _create_goal(client, auth_header, "Small Goal", 100)
    updated = _deposit(client, auth_header, goal["id"], 200)
    # Current capped at target
    assert updated["current_amount"] == 100
    assert updated["status"] == "COMPLETED"
    assert updated["progress_pct"] == 100.0


def test_deposit_rejected_on_completed_goal(client, auth_header):
    goal = _create_goal(client, auth_header, "Done", 50)
    _deposit(client, auth_header, goal["id"], 50)  # completes it
    r = client.post(
        f"/savings/goals/{goal['id']}/deposit",
        json={"amount": 10},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "active" in r.get_json().get("error", "").lower()


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

def test_milestones_empty_initially(client, auth_header):
    goal = _create_goal(client, auth_header, "Fresh", 200)
    r = client.get(f"/savings/goals/{goal['id']}/milestones", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_milestones_recorded_on_deposit(client, auth_header):
    goal = _create_goal(client, auth_header, "Big Goal", 1000)
    _deposit(client, auth_header, goal["id"], 500)   # 50%
    r = client.get(f"/savings/goals/{goal['id']}/milestones", headers=auth_header)
    pcts = {m["pct"] for m in r.get_json()}
    assert 25 in pcts
    assert 50 in pcts
    assert 75 not in pcts


def test_milestones_all_four_at_completion(client, auth_header):
    goal = _create_goal(client, auth_header, "Complete", 100)
    _deposit(client, auth_header, goal["id"], 100)
    r = client.get(f"/savings/goals/{goal['id']}/milestones", headers=auth_header)
    pcts = {m["pct"] for m in r.get_json()}
    assert pcts == {25, 50, 75, 100}


def test_milestones_not_duplicated(client, auth_header):
    """Depositing past a threshold twice must not create duplicate milestone rows."""
    goal = _create_goal(client, auth_header, "NoDup", 100)
    _deposit(client, auth_header, goal["id"], 30)   # crosses 25%
    _deposit(client, auth_header, goal["id"], 30)   # still below 75%
    r = client.get(f"/savings/goals/{goal['id']}/milestones", headers=auth_header)
    milestones = r.get_json()
    pcts = [m["pct"] for m in milestones]
    assert len(pcts) == len(set(pcts)), "Duplicate milestones recorded"


# ---------------------------------------------------------------------------
# build_savings_goal service unit test (no HTTP layer)
# ---------------------------------------------------------------------------

def test_service_goal_to_dict_structure(client, auth_header, app_fixture):
    """goal_to_dict returns all required keys."""
    from app.extensions import db
    from app.models import User
    from app.services.savings import create_goal, goal_to_dict

    with app_fixture.app_context():
        user = db.session.query(User).filter_by(email="test@example.com").first()
        goal, err = create_goal(user.id, {"name": "Service Test", "target_amount": 500})
        assert err is None
        d = goal_to_dict(goal)

    required = {"id", "name", "description", "target_amount", "current_amount",
                "progress_pct", "target_date", "status", "currency", "created_at", "updated_at"}
    assert required.issubset(d.keys())
