"""Tests for goal-based savings tracking — issue #133."""

from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_goal(client, auth_header, **overrides):
    payload = {
        "name": "Emergency Fund",
        "target_amount": 1000.00,
        "currency": "USD",
        "auto_milestones": False,
        **overrides,
    }
    return client.post("/goals", json=payload, headers=auth_header)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def test_create_and_list_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 1000.00
    assert data["current_amount"] == 0.00
    assert data["status"] == "ACTIVE"
    assert data["progress_pct"] == 0.0

    r = client.get("/goals", headers=auth_header)
    assert r.status_code == 200
    goals = r.get_json()
    assert any(g["name"] == "Emergency Fund" for g in goals)


def test_get_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    r = client.get(f"/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == goal_id


def test_get_goal_not_found(client, auth_header):
    r = client.get("/goals/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    r = client.patch(
        f"/goals/{goal_id}",
        json={"name": "Vacation Fund", "target_amount": 2000},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "Vacation Fund"
    assert data["target_amount"] == 2000.00


def test_delete_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    r = client.delete(f"/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    r = client.get(f"/goals/{goal_id}", headers=auth_header)
    assert r.status_code == 404


def test_create_goal_missing_name(client, auth_header):
    r = client.post(
        "/goals",
        json={"target_amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_create_goal_invalid_target(client, auth_header):
    r = client.post(
        "/goals",
        json={"name": "Bad Goal", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_create_goal_with_deadline(client, auth_header):
    future = (date.today() + timedelta(days=90)).isoformat()
    r = _create_goal(client, auth_header, deadline=future)
    assert r.status_code == 201
    assert r.get_json()["deadline"] == future


def test_filter_goals_by_status(client, auth_header):
    _create_goal(client, auth_header, name="Active Goal")
    r = client.get("/goals?status=active", headers=auth_header)
    assert r.status_code == 200
    for g in r.get_json():
        assert g["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# Deposits
# ---------------------------------------------------------------------------

def test_deposit_updates_current_amount(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000)
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/goals/{goal_id}/deposit",
        json={"amount": 250, "note": "First paycheck"},
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["goal"]["current_amount"] == 250.00
    assert body["goal"]["progress_pct"] == 25.0
    assert body["deposit"]["amount"] == 250.00
    assert body["deposit"]["note"] == "First paycheck"


def test_multiple_deposits_accumulate(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000)
    goal_id = r.get_json()["id"]

    client.post(f"/goals/{goal_id}/deposit", json={"amount": 300}, headers=auth_header)
    client.post(f"/goals/{goal_id}/deposit", json={"amount": 200}, headers=auth_header)
    r = client.post(
        f"/goals/{goal_id}/deposit", json={"amount": 100}, headers=auth_header
    )
    assert r.get_json()["goal"]["current_amount"] == 600.00


def test_deposit_auto_completes_goal(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=500)
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/goals/{goal_id}/deposit", json={"amount": 500}, headers=auth_header
    )
    assert r.status_code == 200
    assert r.get_json()["goal"]["status"] == "COMPLETED"


def test_deposit_invalid_amount(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/goals/{goal_id}/deposit", json={"amount": -50}, headers=auth_header
    )
    assert r.status_code == 400


def test_list_deposits(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    client.post(f"/goals/{goal_id}/deposit", json={"amount": 100}, headers=auth_header)
    client.post(f"/goals/{goal_id}/deposit", json={"amount": 200}, headers=auth_header)

    r = client.get(f"/goals/{goal_id}/deposits", headers=auth_header)
    assert r.status_code == 200
    deposits = r.get_json()
    assert len(deposits) == 2
    amounts = {d["amount"] for d in deposits}
    assert amounts == {100.0, 200.0}


def test_deposit_to_cancelled_goal_blocked(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    client.patch(
        f"/goals/{goal_id}", json={"status": "CANCELLED"}, headers=auth_header
    )
    r = client.post(
        f"/goals/{goal_id}/deposit", json={"amount": 50}, headers=auth_header
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

def test_auto_milestones_created(client, auth_header):
    r = _create_goal(client, auth_header, auto_milestones=True)
    assert r.status_code == 201
    milestones = r.get_json()["milestones"]
    pcts = {m["target_pct"] for m in milestones}
    assert pcts == {25.0, 50.0, 75.0, 100.0}


def test_milestone_reached_on_deposit(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000, auto_milestones=True)
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/goals/{goal_id}/deposit", json={"amount": 250}, headers=auth_header
    )
    body = r.get_json()
    # 25% milestone should be reached
    reached = body["milestones_reached"]
    assert any(m["target_pct"] == 25.0 for m in reached)

    # Check the goal's milestone list reflects the change
    goal_data = body["goal"]
    reached_ms = [m for m in goal_data["milestones"] if m["reached"]]
    assert any(m["target_pct"] == 25.0 for m in reached_ms)


def test_add_custom_milestone(client, auth_header):
    r = _create_goal(client, auth_header, auto_milestones=False)
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/goals/{goal_id}/milestones",
        json={"label": "Half way", "target_pct": 50},
        headers=auth_header,
    )
    assert r.status_code == 201
    m = r.get_json()
    assert m["label"] == "Half way"
    assert m["target_pct"] == 50.0


def test_delete_milestone(client, auth_header):
    r = _create_goal(client, auth_header, auto_milestones=True)
    goal_id = r.get_json()["id"]
    milestone_id = r.get_json()["milestones"][0]["id"]

    r = client.delete(
        f"/goals/{goal_id}/milestones/{milestone_id}", headers=auth_header
    )
    assert r.status_code == 200

    r = client.get(f"/goals/{goal_id}", headers=auth_header)
    remaining_ids = [m["id"] for m in r.get_json()["milestones"]]
    assert milestone_id not in remaining_ids


def test_add_milestone_invalid_pct(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    r = client.post(
        f"/goals/{goal_id}/milestones",
        json={"label": "Too high", "target_pct": 150},
        headers=auth_header,
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Isolation — user A cannot see user B's goals
# ---------------------------------------------------------------------------

def test_goal_isolation_between_users(client):
    # Register user A
    client.post("/auth/register", json={"email": "a@test.com", "password": "pw123456"})
    r = client.post("/auth/login", json={"email": "a@test.com", "password": "pw123456"})
    token_a = r.get_json()["access_token"]
    header_a = {"Authorization": f"Bearer {token_a}"}

    # Register user B
    client.post("/auth/register", json={"email": "b@test.com", "password": "pw123456"})
    r = client.post("/auth/login", json={"email": "b@test.com", "password": "pw123456"})
    token_b = r.get_json()["access_token"]
    header_b = {"Authorization": f"Bearer {token_b}"}

    # A creates a goal
    r = client.post(
        "/goals",
        json={"name": "A's Secret Fund", "target_amount": 999},
        headers=header_a,
    )
    goal_id = r.get_json()["id"]

    # B cannot see A's goal
    r = client.get(f"/goals/{goal_id}", headers=header_b)
    assert r.status_code == 404

    # B's goal list is empty
    r = client.get("/goals", headers=header_b)
    assert r.get_json() == []
