"""Tests for savings goals: model, CRUD endpoints, milestone logic, progress."""
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_goal(client, auth_header, **kwargs):
    payload = {"name": "Emergency Fund", "target_amount": 1000, **kwargs}
    return client.post("/savings-goals", json=payload, headers=auth_header)


# ---------------------------------------------------------------------------
# Model / unit-level milestone logic
# ---------------------------------------------------------------------------

def test_achieved_milestones_none(app_fixture):
    from app.models import SavingsGoal
    with app_fixture.app_context():
        g = SavingsGoal(
            user_id=1, name="Test", target_amount=1000, current_amount=0,
            currency="USD", status="active",
        )
        assert g.achieved_milestones() == []


def test_achieved_milestones_partial(app_fixture):
    from app.models import SavingsGoal
    with app_fixture.app_context():
        g = SavingsGoal(
            user_id=1, name="Test", target_amount=1000, current_amount=250,
            currency="USD", status="active",
        )
        assert g.achieved_milestones() == [25]


def test_achieved_milestones_half(app_fixture):
    from app.models import SavingsGoal
    with app_fixture.app_context():
        g = SavingsGoal(
            user_id=1, name="Test", target_amount=1000, current_amount=500,
            currency="USD", status="active",
        )
        assert g.achieved_milestones() == [25, 50]


def test_achieved_milestones_three_quarters(app_fixture):
    from app.models import SavingsGoal
    with app_fixture.app_context():
        g = SavingsGoal(
            user_id=1, name="Test", target_amount=1000, current_amount=750,
            currency="USD", status="active",
        )
        assert g.achieved_milestones() == [25, 50, 75]


def test_achieved_milestones_full(app_fixture):
    from app.models import SavingsGoal
    with app_fixture.app_context():
        g = SavingsGoal(
            user_id=1, name="Test", target_amount=1000, current_amount=1000,
            currency="USD", status="active",
        )
        assert g.achieved_milestones() == [25, 50, 75, 100]


def test_achieved_milestones_over_target(app_fixture):
    from app.models import SavingsGoal
    with app_fixture.app_context():
        g = SavingsGoal(
            user_id=1, name="Test", target_amount=1000, current_amount=1200,
            currency="USD", status="active",
        )
        assert g.achieved_milestones() == [25, 50, 75, 100]


def test_achieved_milestones_zero_target(app_fixture):
    from app.models import SavingsGoal
    with app_fixture.app_context():
        g = SavingsGoal(
            user_id=1, name="Test", target_amount=0, current_amount=0,
            currency="USD", status="active",
        )
        assert g.achieved_milestones() == []


# ---------------------------------------------------------------------------
# CRUD — create
# ---------------------------------------------------------------------------

def test_create_goal_minimal(client, auth_header):
    r = _create_goal(client, auth_header)
    assert r.status_code == 201
    body = r.get_json()
    assert body["id"] is not None
    assert body["name"] == "Emergency Fund"
    assert body["target_amount"] == 1000.0
    assert body["current_amount"] == 0.0
    assert body["currency"] == "USD"
    assert body["status"] == "active"
    assert body["achieved_milestones"] == []
    assert body["deadline"] is None


def test_create_goal_with_all_fields(client, auth_header):
    deadline = (date.today() + timedelta(days=90)).isoformat()
    r = _create_goal(
        client, auth_header,
        current_amount=300,
        deadline=deadline,
        currency="EUR",
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["current_amount"] == 300.0
    assert body["currency"] == "EUR"
    assert body["deadline"] == deadline
    assert body["achieved_milestones"] == [25]


def test_create_goal_auto_completes_when_full(client, auth_header):
    r = _create_goal(client, auth_header, current_amount=1000)
    assert r.status_code == 201
    body = r.get_json()
    assert body["status"] == "completed"
    assert body["achieved_milestones"] == [25, 50, 75, 100]


def test_create_goal_missing_name(client, auth_header):
    r = client.post("/savings-goals", json={"target_amount": 500}, headers=auth_header)
    assert r.status_code == 400


def test_create_goal_missing_target(client, auth_header):
    r = client.post("/savings-goals", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 400


def test_create_goal_negative_target(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=-100)
    assert r.status_code == 400


def test_create_goal_negative_current(client, auth_header):
    r = _create_goal(client, auth_header, current_amount=-50)
    assert r.status_code == 400


def test_create_goal_invalid_deadline(client, auth_header):
    r = _create_goal(client, auth_header, deadline="not-a-date")
    assert r.status_code == 400


def test_create_goal_requires_auth(client):
    r = client.post("/savings-goals", json={"name": "Test", "target_amount": 100})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# CRUD — list
# ---------------------------------------------------------------------------

def test_list_goals_empty(client, auth_header):
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_goals(client, auth_header):
    _create_goal(client, auth_header, name="Goal A")
    _create_goal(client, auth_header, name="Goal B")
    r = client.get("/savings-goals", headers=auth_header)
    assert r.status_code == 200
    names = [g["name"] for g in r.get_json()]
    assert "Goal A" in names
    assert "Goal B" in names


def test_list_goals_filter_by_status(client, auth_header):
    _create_goal(client, auth_header, name="Active Goal")
    _create_goal(client, auth_header, name="Full Goal", current_amount=1000)
    r = client.get("/savings-goals?status=active", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert all(g["status"] == "active" for g in items)
    assert any(g["name"] == "Active Goal" for g in items)


def test_list_goals_requires_auth(client):
    r = client.get("/savings-goals")
    assert r.status_code == 401


def test_list_goals_user_isolation(client, auth_header):
    """Goals belong only to the owning user."""
    _create_goal(client, auth_header, name="My Goal")

    # Create second user
    client.post("/auth/register", json={"email": "other@example.com", "password": "pass1234"})
    r2 = client.post("/auth/login", json={"email": "other@example.com", "password": "pass1234"})
    other_header = {"Authorization": f"Bearer {r2.get_json()['access_token']}"}

    r = client.get("/savings-goals", headers=other_header)
    assert r.status_code == 200
    assert r.get_json() == []


# ---------------------------------------------------------------------------
# CRUD — get single
# ---------------------------------------------------------------------------

def test_get_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == goal_id


def test_get_goal_not_found(client, auth_header):
    r = client.get("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404


def test_get_goal_other_user(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    client.post("/auth/register", json={"email": "eve@example.com", "password": "pass1234"})
    r2 = client.post("/auth/login", json={"email": "eve@example.com", "password": "pass1234"})
    other_header = {"Authorization": f"Bearer {r2.get_json()['access_token']}"}

    r = client.get(f"/savings-goals/{goal_id}", headers=other_header)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# CRUD — update
# ---------------------------------------------------------------------------

def test_update_goal_name(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    r = client.put(f"/savings-goals/{goal_id}", json={"name": "Renamed"}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Renamed"


def test_update_goal_current_amount_triggers_milestone(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000)
    goal_id = r.get_json()["id"]

    r = client.put(f"/savings-goals/{goal_id}", json={"current_amount": 500}, headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert body["achieved_milestones"] == [25, 50]
    assert body["status"] == "active"


def test_update_goal_auto_completes_at_100_percent(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=500)
    goal_id = r.get_json()["id"]

    r = client.put(f"/savings-goals/{goal_id}", json={"current_amount": 500}, headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "completed"
    assert 100 in body["achieved_milestones"]


def test_update_goal_cancel(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    r = client.put(f"/savings-goals/{goal_id}", json={"status": "cancelled"}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["status"] == "cancelled"


def test_update_goal_invalid_status(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    r = client.put(f"/savings-goals/{goal_id}", json={"status": "bogus"}, headers=auth_header)
    assert r.status_code == 400


def test_update_goal_not_found(client, auth_header):
    r = client.put("/savings-goals/99999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404


def test_update_goal_clears_deadline(client, auth_header):
    deadline = (date.today() + timedelta(days=30)).isoformat()
    r = _create_goal(client, auth_header, deadline=deadline)
    goal_id = r.get_json()["id"]

    r = client.put(f"/savings-goals/{goal_id}", json={"deadline": None}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["deadline"] is None


# ---------------------------------------------------------------------------
# CRUD — delete
# ---------------------------------------------------------------------------

def test_delete_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    r = client.delete(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["status"] == "cancelled"


def test_delete_goal_not_found(client, auth_header):
    r = client.delete("/savings-goals/99999", headers=auth_header)
    assert r.status_code == 404


def test_delete_goal_other_user(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    client.post("/auth/register", json={"email": "attacker@example.com", "password": "pass1234"})
    r2 = client.post("/auth/login", json={"email": "attacker@example.com", "password": "pass1234"})
    other_header = {"Authorization": f"Bearer {r2.get_json()['access_token']}"}

    r = client.delete(f"/savings-goals/{goal_id}", headers=other_header)
    assert r.status_code == 404

    # Original user can still see it
    r = client.get(f"/savings-goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Progress endpoint
# ---------------------------------------------------------------------------

def test_progress_no_deadline(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000, current_amount=400)
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings-goals/{goal_id}/progress", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert body["percentage_complete"] == 40.0
    assert body["remaining_amount"] == 600.0
    assert body["days_left"] is None
    assert body["on_track"] is None
    assert body["achieved_milestones"] == [25]


def test_progress_with_future_deadline_on_track(client, auth_header):
    """Goal started today, deadline far away, already 50% done → on track."""
    deadline = (date.today() + timedelta(days=60)).isoformat()
    r = _create_goal(client, auth_header, target_amount=1000, current_amount=500, deadline=deadline)
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings-goals/{goal_id}/progress", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert body["days_left"] > 0
    assert body["percentage_complete"] == 50.0
    assert body["remaining_amount"] == 500.0
    # Created just now, so elapsed≈0 ⟹ expected_pct≈0 ⟹ on_track=True
    assert body["on_track"] is True


def test_progress_with_past_deadline_not_complete(client, auth_header):
    """Deadline in the past, not yet 100% → not on track."""
    past = (date.today() - timedelta(days=1)).isoformat()
    r = _create_goal(client, auth_header, target_amount=1000, current_amount=400, deadline=past)
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings-goals/{goal_id}/progress", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert body["days_left"] < 0
    assert body["on_track"] is False


def test_progress_with_past_deadline_complete(client, auth_header):
    """Deadline in the past, current == target → on track (already done)."""
    past = (date.today() - timedelta(days=1)).isoformat()
    r = _create_goal(client, auth_header, target_amount=1000, current_amount=1000, deadline=past)
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings-goals/{goal_id}/progress", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["on_track"] is True


def test_progress_100_percent(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=500, current_amount=500)
    goal_id = r.get_json()["id"]

    r = client.get(f"/savings-goals/{goal_id}/progress", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert body["percentage_complete"] == 100.0
    assert body["remaining_amount"] == 0.0
    assert body["achieved_milestones"] == [25, 50, 75, 100]


def test_progress_not_found(client, auth_header):
    r = client.get("/savings-goals/99999/progress", headers=auth_header)
    assert r.status_code == 404


def test_progress_requires_auth(client):
    r = client.get("/savings-goals/1/progress")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Milestone boundary checks
# ---------------------------------------------------------------------------

def test_milestone_at_exactly_25(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=100, current_amount=25)
    assert 25 in r.get_json()["achieved_milestones"]


def test_milestone_just_below_25(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=100, current_amount=24.99)
    assert r.get_json()["achieved_milestones"] == []


def test_milestone_at_exactly_50(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=100, current_amount=50)
    assert r.get_json()["achieved_milestones"] == [25, 50]


def test_milestone_at_exactly_75(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=100, current_amount=75)
    assert r.get_json()["achieved_milestones"] == [25, 50, 75]


def test_milestone_just_below_100(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=100, current_amount=99.99)
    assert 100 not in r.get_json()["achieved_milestones"]


def test_milestone_after_update(client, auth_header):
    """Milestone should update when current_amount changes via PUT."""
    r = _create_goal(client, auth_header, target_amount=200)
    goal_id = r.get_json()["id"]
    assert r.get_json()["achieved_milestones"] == []

    # Reach 50%
    r = client.put(f"/savings-goals/{goal_id}", json={"current_amount": 100}, headers=auth_header)
    assert r.get_json()["achieved_milestones"] == [25, 50]

    # Reach 75%
    r = client.put(f"/savings-goals/{goal_id}", json={"current_amount": 150}, headers=auth_header)
    assert r.get_json()["achieved_milestones"] == [25, 50, 75]
