"""Tests for goal-based savings tracking."""

from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_login(client, email="saver@example.com", password="password123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_goal(client, header, **kwargs):
    payload = {"name": "Emergency Fund", "target_amount": 5000.00, **kwargs}
    return client.post("/savings", json=payload, headers=header)


# ---------------------------------------------------------------------------
# CRUD — Goals
# ---------------------------------------------------------------------------


def test_list_goals_empty(client, auth_header):
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_goal_minimal(client, auth_header):
    r = _create_goal(client, auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 5000.0
    assert data["current_amount"] == 0.0
    assert data["progress_pct"] == 0.0
    assert data["status"] == "ACTIVE"
    assert data["milestones_reached"] == []


def test_create_goal_with_deadline_and_color(client, auth_header):
    deadline = (date.today() + timedelta(days=180)).isoformat()
    r = _create_goal(
        client,
        auth_header,
        name="Vacation Fund",
        target_amount=3000,
        deadline=deadline,
        color="#f59e0b",
        icon="plane",
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["deadline"] == deadline
    assert data["color"] == "#f59e0b"
    assert data["icon"] == "plane"


def test_create_goal_missing_name(client, auth_header):
    r = client.post("/savings", json={"target_amount": 1000}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json().get("error", "")


def test_create_goal_missing_target(client, auth_header):
    r = client.post("/savings", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 400


def test_create_goal_negative_target(client, auth_header):
    r = client.post(
        "/savings", json={"name": "Bad", "target_amount": -100}, headers=auth_header
    )
    assert r.status_code == 400


def test_list_goals_shows_own_goals(client, auth_header):
    _create_goal(client, auth_header, name="Goal A")
    _create_goal(client, auth_header, name="Goal B")
    r = client.get("/savings", headers=auth_header)
    assert r.status_code == 200
    names = [g["name"] for g in r.get_json()]
    assert "Goal A" in names
    assert "Goal B" in names


def test_get_goal_detail(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == goal_id
    assert "deposits" in data


def test_get_goal_not_found(client, auth_header):
    r = client.get("/savings/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_goal_name_and_target(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]
    r = client.patch(
        f"/savings/{goal_id}",
        json={"name": "Renamed", "target_amount": 8000},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "Renamed"
    assert data["target_amount"] == 8000.0


def test_update_goal_status_pause_resume(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]
    r = client.patch(
        f"/savings/{goal_id}", json={"status": "PAUSED"}, headers=auth_header
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "PAUSED"
    r = client.patch(
        f"/savings/{goal_id}", json={"status": "ACTIVE"}, headers=auth_header
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "ACTIVE"


def test_update_goal_invalid_status(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]
    r = client.patch(
        f"/savings/{goal_id}", json={"status": "INVALID"}, headers=auth_header
    )
    assert r.status_code == 400


def test_delete_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]
    r = client.delete(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Deposits
# ---------------------------------------------------------------------------


def test_add_deposit_updates_balance(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000)
    goal_id = r.get_json()["id"]
    r = client.post(
        f"/savings/{goal_id}/deposits",
        json={"amount": 250.00, "note": "First save"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["deposit"]["amount"] == 250.0
    assert data["goal"]["current_amount"] == 250.0
    assert data["goal"]["progress_pct"] == 25.0


def test_deposit_auto_completes_at_100pct(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=500)
    goal_id = r.get_json()["id"]
    r = client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 500}, headers=auth_header
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["goal"]["status"] == "COMPLETED"
    assert 100 in data["milestones_newly_reached"]


def test_deposit_incremental_milestones(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000)
    goal_id = r.get_json()["id"]

    # 25% milestone
    r = client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 250}, headers=auth_header
    )
    assert r.status_code == 201
    assert 25 in r.get_json()["milestones_newly_reached"]

    # 50% milestone
    r = client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 250}, headers=auth_header
    )
    assert 50 in r.get_json()["milestones_newly_reached"]

    # 75% milestone
    r = client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 250}, headers=auth_header
    )
    assert 75 in r.get_json()["milestones_newly_reached"]

    # 100% milestone
    r = client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 250}, headers=auth_header
    )
    assert 100 in r.get_json()["milestones_newly_reached"]


def test_deposit_goal_response_has_all_milestones_reached(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000)
    goal_id = r.get_json()["id"]
    client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 600}, headers=auth_header
    )
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    data = r.get_json()
    assert 25 in data["milestones_reached"]
    assert 50 in data["milestones_reached"]
    assert 75 not in data["milestones_reached"]


def test_deposit_negative_amount_rejected(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]
    r = client.post(
        f"/savings/{goal_id}/deposits", json={"amount": -50}, headers=auth_header
    )
    assert r.status_code == 400


def test_deposit_zero_amount_rejected(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]
    r = client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 0}, headers=auth_header
    )
    assert r.status_code == 400


def test_deposit_to_completed_goal_rejected(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=100)
    goal_id = r.get_json()["id"]
    client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 100}, headers=auth_header
    )
    r = client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 10}, headers=auth_header
    )
    assert r.status_code == 400


def test_deposit_to_paused_goal_rejected(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]
    client.patch(f"/savings/{goal_id}", json={"status": "PAUSED"}, headers=auth_header)
    r = client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 100}, headers=auth_header
    )
    assert r.status_code == 400


def test_list_deposits(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000)
    goal_id = r.get_json()["id"]
    client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 100}, headers=auth_header
    )
    client.post(
        f"/savings/{goal_id}/deposits",
        json={"amount": 200, "note": "Bonus"},
        headers=auth_header,
    )
    r = client.get(f"/savings/{goal_id}/deposits", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 2
    amounts = {d["amount"] for d in data}
    assert 100.0 in amounts
    assert 200.0 in amounts


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_empty(client, auth_header):
    r = client.get("/savings/summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_goals"] == 0
    assert data["total_saved"] == 0.0
    assert data["overall_progress_pct"] == 0.0


def test_summary_with_goals(client, auth_header):
    _create_goal(client, auth_header, name="Goal A", target_amount=1000)
    r2 = _create_goal(client, auth_header, name="Goal B", target_amount=2000)
    g2_id = r2.get_json()["id"]
    client.post(f"/savings/{g2_id}/deposits", json={"amount": 500}, headers=auth_header)

    r = client.get("/savings/summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_goals"] == 2
    assert data["total_target"] == 3000.0
    assert data["total_saved"] == 500.0
    assert data["active_goals"] == 2
    assert data["completed_goals"] == 0


# ---------------------------------------------------------------------------
# Auth isolation
# ---------------------------------------------------------------------------


def test_cannot_access_other_users_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    other_header = _register_and_login(client, email="other@example.com")
    r = client.get(f"/savings/{goal_id}", headers=other_header)
    assert r.status_code == 404


def test_cannot_deposit_to_other_users_goal(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000)
    goal_id = r.get_json()["id"]

    other_header = _register_and_login(client, email="other2@example.com")
    r = client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 100}, headers=other_header
    )
    assert r.status_code == 404


def test_cannot_delete_other_users_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    goal_id = r.get_json()["id"]

    other_header = _register_and_login(client, email="other3@example.com")
    r = client.delete(f"/savings/{goal_id}", headers=other_header)
    assert r.status_code == 404

    # Original owner can still access
    r = client.get(f"/savings/{goal_id}", headers=auth_header)
    assert r.status_code == 200


def test_other_user_goals_not_in_list(client, auth_header):
    _create_goal(client, auth_header, name="My Goal")

    other_header = _register_and_login(client, email="other4@example.com")
    r = client.get("/savings", headers=other_header)
    assert r.status_code == 200
    assert r.get_json() == []


# ---------------------------------------------------------------------------
# Progress & fields
# ---------------------------------------------------------------------------


def test_goal_defaults_to_user_currency(client):
    h = _register_and_login(client, email="currency@example.com")
    client.patch("/auth/me", json={"preferred_currency": "EUR"}, headers=h)
    r = client.post(
        "/savings", json={"name": "Euro Goal", "target_amount": 500}, headers=h
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


def test_goal_completion_when_target_lowered(client, auth_header):
    """Updating target_amount below current_amount should auto-complete goal."""
    r = _create_goal(client, auth_header, target_amount=1000)
    goal_id = r.get_json()["id"]
    client.post(
        f"/savings/{goal_id}/deposits", json={"amount": 600}, headers=auth_header
    )
    r = client.patch(
        f"/savings/{goal_id}", json={"target_amount": 600}, headers=auth_header
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "COMPLETED"
