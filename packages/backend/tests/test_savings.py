"""Comprehensive tests for Savings Goals & Contributions endpoints."""
from datetime import date, timedelta


def _create_goal(client, auth_header, **overrides):
    """Helper to create a savings goal with sensible defaults."""
    payload = {
        "name": "Emergency Fund",
        "target_amount": 5000,
        "currency": "USD",
        "deadline": (date.today() + timedelta(days=180)).isoformat(),
        "color": "#22C55E",
        "icon": "shield",
    }
    payload.update(overrides)
    return client.post("/savings/goals", json=payload, headers=auth_header)


# ── List / Create ───────────────────────────────────────────────────────


def test_list_goals_empty(client, auth_header):
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    assert r.status_code == 201
    body = r.get_json()
    assert body["name"] == "Emergency Fund"
    assert body["target_amount"] == 5000
    assert body["current_amount"] == 0
    assert body["progress"] == 0
    assert body["completed"] is False
    assert body["color"] == "#22C55E"
    assert body["icon"] == "shield"


def test_create_goal_minimal(client, auth_header):
    """Only name and target_amount are required."""
    r = client.post(
        "/savings/goals",
        json={"name": "Vacation", "target_amount": 1200},
        headers=auth_header,
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["name"] == "Vacation"
    assert body["deadline"] is None


def test_create_goal_validation_missing_name(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"target_amount": 1000},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_create_goal_validation_bad_target(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Bad", "target_amount": -100},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_create_goal_validation_zero_target(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Zero", "target_amount": 0},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_create_goal_bad_deadline(client, auth_header):
    r = client.post(
        "/savings/goals",
        json={"name": "Bad Date", "target_amount": 100, "deadline": "not-a-date"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_list_goals_returns_created(client, auth_header):
    _create_goal(client, auth_header, name="Goal A")
    _create_goal(client, auth_header, name="Goal B")
    r = client.get("/savings/goals", headers=auth_header)
    assert r.status_code == 200
    names = [g["name"] for g in r.get_json()]
    assert "Goal A" in names
    assert "Goal B" in names


# ── Update ──────────────────────────────────────────────────────────────


def test_update_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    gid = r.get_json()["id"]

    r = client.put(
        f"/savings/goals/{gid}",
        json={"name": "Renamed Fund", "target_amount": 10000, "color": "#EF4444"},
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["name"] == "Renamed Fund"
    assert body["target_amount"] == 10000
    assert body["color"] == "#EF4444"


def test_update_goal_not_found(client, auth_header):
    r = client.put(
        "/savings/goals/9999",
        json={"name": "Nope"},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_update_goal_clear_deadline(client, auth_header):
    r = _create_goal(client, auth_header)
    gid = r.get_json()["id"]
    r = client.put(
        f"/savings/goals/{gid}",
        json={"deadline": None},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["deadline"] is None


# ── Delete ──────────────────────────────────────────────────────────────


def test_delete_goal(client, auth_header):
    r = _create_goal(client, auth_header)
    gid = r.get_json()["id"]
    r = client.delete(f"/savings/goals/{gid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # Verify removed
    r = client.get("/savings/goals", headers=auth_header)
    assert all(g["id"] != gid for g in r.get_json())


def test_delete_goal_not_found(client, auth_header):
    r = client.delete("/savings/goals/9999", headers=auth_header)
    assert r.status_code == 404


# ── Contributions ───────────────────────────────────────────────────────


def test_contribute_to_goal(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000)
    gid = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 250, "notes": "Birthday money"},
        headers=auth_header,
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["contribution"]["amount"] == 250
    assert body["contribution"]["notes"] == "Birthday money"
    assert body["goal"]["current_amount"] == 250
    assert body["goal"]["progress"] == 25.0
    assert body["just_completed"] is False


def test_contribute_bad_amount(client, auth_header):
    r = _create_goal(client, auth_header)
    gid = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": -50},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_contribute_missing_amount(client, auth_header):
    r = _create_goal(client, auth_header)
    gid = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_contribute_goal_not_found(client, auth_header):
    r = client.post(
        "/savings/goals/9999/contribute",
        json={"amount": 100},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_contribute_auto_completes_goal(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=500)
    gid = r.get_json()["id"]

    # Contribute exactly the target
    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["just_completed"] is True
    assert body["goal"]["completed"] is True
    assert body["goal"]["completed_at"] is not None
    assert body["goal"]["progress"] == 100.0


def test_contribute_over_target_completes(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=100)
    gid = r.get_json()["id"]

    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 150},
        headers=auth_header,
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["just_completed"] is True
    assert body["goal"]["completed"] is True


def test_multiple_contributions_accumulate(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=1000)
    gid = r.get_json()["id"]

    for amt in [200, 300, 100]:
        client.post(
            f"/savings/goals/{gid}/contribute",
            json={"amount": amt},
            headers=auth_header,
        )

    r = client.get("/savings/goals", headers=auth_header)
    goal = next(g for g in r.get_json() if g["id"] == gid)
    assert goal["current_amount"] == 600
    assert goal["progress"] == 60.0
    assert goal["completed"] is False


def test_list_contributions(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=5000)
    gid = r.get_json()["id"]

    client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 100, "notes": "First"},
        headers=auth_header,
    )
    client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 200, "notes": "Second"},
        headers=auth_header,
    )

    r = client.get(f"/savings/goals/{gid}/contributions", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 2
    amounts = [c["amount"] for c in items]
    assert 100 in amounts
    assert 200 in amounts


def test_list_contributions_goal_not_found(client, auth_header):
    r = client.get("/savings/goals/9999/contributions", headers=auth_header)
    assert r.status_code == 404


def test_contribute_custom_date(client, auth_header):
    r = _create_goal(client, auth_header, target_amount=5000)
    gid = r.get_json()["id"]

    past = (date.today() - timedelta(days=7)).isoformat()
    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 50, "contributed_at": past},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["contribution"]["contributed_at"] == past


# ── Summary ─────────────────────────────────────────────────────────────


def test_summary_empty(client, auth_header):
    r = client.get("/savings/goals/summary", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_saved"] == 0
    assert body["goals_count"] == 0
    assert body["completed_count"] == 0
    assert body["nearest_deadline"] is None


def test_summary_with_data(client, auth_header):
    deadline_soon = (date.today() + timedelta(days=30)).isoformat()
    deadline_far = (date.today() + timedelta(days=365)).isoformat()

    _create_goal(client, auth_header, name="Soon", target_amount=500, deadline=deadline_soon)
    r = _create_goal(client, auth_header, name="Far", target_amount=1000, deadline=deadline_far)
    far_id = r.get_json()["id"]

    r2 = _create_goal(client, auth_header, name="Quick", target_amount=100)
    quick_id = r2.get_json()["id"]

    # Contribute to complete "Quick"
    client.post(
        f"/savings/goals/{quick_id}/contribute",
        json={"amount": 100},
        headers=auth_header,
    )

    # Contribute partial to "Far"
    client.post(
        f"/savings/goals/{far_id}/contribute",
        json={"amount": 250},
        headers=auth_header,
    )

    r = client.get("/savings/goals/summary", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert body["goals_count"] == 3
    assert body["completed_count"] == 1
    assert body["active_count"] == 2
    assert body["total_saved"] == 350  # 100 + 250
    assert body["nearest_deadline"] is not None
    assert body["nearest_deadline"]["deadline"] == deadline_soon


# ── Auth required ───────────────────────────────────────────────────────


def test_goals_require_auth(client):
    for method, path in [
        ("GET", "/savings/goals"),
        ("POST", "/savings/goals"),
        ("GET", "/savings/goals/summary"),
    ]:
        r = getattr(client, method.lower())(path)
        assert r.status_code in (401, 422), f"{method} {path} should require auth"


def test_delete_goal_cascades_contributions(client, auth_header):
    """Deleting a goal should also remove its contributions."""
    r = _create_goal(client, auth_header, target_amount=1000)
    gid = r.get_json()["id"]

    client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 100},
        headers=auth_header,
    )

    r = client.delete(f"/savings/goals/{gid}", headers=auth_header)
    assert r.status_code == 200

    # Contributions endpoint should 404 since goal is gone
    r = client.get(f"/savings/goals/{gid}/contributions", headers=auth_header)
    assert r.status_code == 404


def test_update_target_triggers_completion(client, auth_header):
    """Lowering target below current_amount should mark goal completed."""
    r = _create_goal(client, auth_header, target_amount=1000)
    gid = r.get_json()["id"]

    # Add contribution
    client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 500},
        headers=auth_header,
    )

    # Lower target to 400 (below current 500)
    r = client.put(
        f"/savings/goals/{gid}",
        json={"target_amount": 400},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["completed"] is True


def test_update_target_uncompletes(client, auth_header):
    """Raising target above current_amount should uncomplete the goal."""
    r = _create_goal(client, auth_header, target_amount=100)
    gid = r.get_json()["id"]

    # Complete it
    client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 100},
        headers=auth_header,
    )

    # Raise target
    r = client.put(
        f"/savings/goals/{gid}",
        json={"target_amount": 500},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["completed"] is False
    assert r.get_json()["completed_at"] is None
