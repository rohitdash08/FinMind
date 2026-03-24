"""Tests for goal-based savings tracking & milestones (Issue #133)."""

import os
import pytest
from datetime import date, timedelta

os.environ.setdefault("FLASK_ENV", "testing")

from app import create_app  # noqa: E402
from app.config import Settings  # noqa: E402
from app.extensions import db, redis_client  # noqa: E402
from app.models import SavingsGoal, SavingsContribution  # noqa: E402


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-savings-32plus-chars-secret-12345"


@pytest.fixture()
def app():
    settings = TestSettings()
    app = create_app(settings)
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
    try:
        redis_client.flushdb()
    except Exception:
        pass
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
    try:
        redis_client.flushdb()
    except Exception:
        pass


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth(client):
    """Register and login, return auth header."""
    client.post(
        "/auth/register",
        json={"email": "saver@test.com", "password": "pass123456"},
    )
    r = client.post(
        "/auth/login",
        json={"email": "saver@test.com", "password": "pass123456"},
    )
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


@pytest.fixture()
def goal(client, auth):
    """Create a default test goal and return its data."""
    r = client.post(
        "/savings/goals",
        json={
            "name": "Vacation Fund",
            "target_amount": 1000.00,
            "currency": "USD",
            "category": "travel",
            "deadline": (date.today() + timedelta(days=180)).isoformat(),
        },
        headers=auth,
    )
    assert r.status_code == 201
    return r.get_json()


# ─── Goal CRUD ─────────────────────────────────────────────────────────────


def test_create_goal(client, auth):
    r = client.post(
        "/savings/goals",
        json={"name": "Emergency Fund", "target_amount": 5000},
        headers=auth,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Emergency Fund"
    assert data["target_amount"] == 5000.0
    assert data["current_amount"] == 0.0
    assert data["status"] == "ACTIVE"
    assert data["progress_pct"] == 0.0
    assert data["remaining"] == 5000.0
    assert data["milestones_reached"] == []


def test_create_goal_validation(client, auth):
    # Missing name
    r = client.post("/savings/goals", json={"target_amount": 100}, headers=auth)
    assert r.status_code == 400

    # Missing target
    r = client.post("/savings/goals", json={"name": "Test"}, headers=auth)
    assert r.status_code == 400

    # Zero target
    r = client.post(
        "/savings/goals", json={"name": "Test", "target_amount": 0}, headers=auth
    )
    assert r.status_code == 400

    # Negative target
    r = client.post(
        "/savings/goals", json={"name": "Test", "target_amount": -100}, headers=auth
    )
    assert r.status_code == 400


def test_list_goals(client, auth, goal):
    r = client.get("/savings/goals", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 1
    assert data[0]["name"] == "Vacation Fund"


def test_list_goals_filter_status(client, auth, goal):
    r = client.get("/savings/goals?status=COMPLETED", headers=auth)
    assert r.status_code == 200
    assert len(r.get_json()) == 0

    r = client.get("/savings/goals?status=ACTIVE", headers=auth)
    assert len(r.get_json()) == 1


def test_get_goal(client, auth, goal):
    gid = goal["id"]
    r = client.get(f"/savings/goals/{gid}", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == gid
    assert "contributions" in data
    assert len(data["contributions"]) == 0


def test_get_goal_not_found(client, auth):
    r = client.get("/savings/goals/99999", headers=auth)
    assert r.status_code == 404


def test_update_goal(client, auth, goal):
    gid = goal["id"]
    r = client.patch(
        f"/savings/goals/{gid}",
        json={"name": "Beach Vacation", "target_amount": 1500},
        headers=auth,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "Beach Vacation"
    assert data["target_amount"] == 1500.0


def test_update_goal_status(client, auth, goal):
    gid = goal["id"]
    r = client.patch(
        f"/savings/goals/{gid}",
        json={"status": "PAUSED"},
        headers=auth,
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "PAUSED"


def test_delete_goal(client, auth, goal):
    gid = goal["id"]
    r = client.delete(f"/savings/goals/{gid}", headers=auth)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    r = client.get(f"/savings/goals/{gid}", headers=auth)
    assert r.status_code == 404


# ─── Contributions ─────────────────────────────────────────────────────────


def test_contribute(client, auth, goal):
    gid = goal["id"]
    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 250, "note": "first deposit"},
        headers=auth,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["current_amount"] == 250.0
    assert data["progress_pct"] == 25.0
    assert data["remaining"] == 750.0
    assert 25 in data["milestones_reached"]
    assert len(data["contributions"]) == 1
    assert data["contributions"][0]["note"] == "first deposit"


def test_contribute_validation(client, auth, goal):
    gid = goal["id"]
    # Zero amount
    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 0},
        headers=auth,
    )
    assert r.status_code == 400

    # Negative amount
    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": -50},
        headers=auth,
    )
    assert r.status_code == 400

    # Missing amount
    r = client.post(f"/savings/goals/{gid}/contribute", json={}, headers=auth)
    assert r.status_code == 400


def test_multiple_contributions_accumulate(client, auth, goal):
    gid = goal["id"]
    client.post(f"/savings/goals/{gid}/contribute", json={"amount": 100}, headers=auth)
    client.post(f"/savings/goals/{gid}/contribute", json={"amount": 150}, headers=auth)
    client.post(f"/savings/goals/{gid}/contribute", json={"amount": 500}, headers=auth)

    r = client.get(f"/savings/goals/{gid}", headers=auth)
    data = r.get_json()
    assert data["current_amount"] == 750.0
    assert data["progress_pct"] == 75.0
    assert sorted(data["milestones_reached"]) == [25, 50, 75]


def test_goal_auto_completes_at_100(client, auth, goal):
    gid = goal["id"]
    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 1000},
        headers=auth,
    )
    data = r.get_json()
    assert data["status"] == "COMPLETED"
    assert data["progress_pct"] == 100.0
    assert data["milestones_reached"] == [25, 50, 75, 100]


def test_contribute_exceeds_target(client, auth, goal):
    """Contributions can exceed the target (over-saving)."""
    gid = goal["id"]
    r = client.post(
        f"/savings/goals/{gid}/contribute",
        json={"amount": 1200},
        headers=auth,
    )
    data = r.get_json()
    assert data["current_amount"] == 1200.0
    assert data["status"] == "COMPLETED"
    assert data["progress_pct"] == 120.0


# ─── Milestones ────────────────────────────────────────────────────────────


def test_milestones_endpoint(client, auth, goal):
    gid = goal["id"]
    client.post(f"/savings/goals/{gid}/contribute", json={"amount": 500}, headers=auth)

    r = client.get(f"/savings/goals/{gid}/milestones", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["progress_pct"] == 50.0
    assert data["next_milestone"] == 75
    assert data["amount_to_next"] == 250.0

    milestones = {m["threshold"]: m for m in data["milestones"]}
    assert milestones[25]["reached"] is True
    assert milestones[50]["reached"] is True
    assert milestones[75]["reached"] is False
    assert milestones[100]["reached"] is False


def test_milestones_all_reached(client, auth, goal):
    gid = goal["id"]
    client.post(f"/savings/goals/{gid}/contribute", json={"amount": 1000}, headers=auth)

    r = client.get(f"/savings/goals/{gid}/milestones", headers=auth)
    data = r.get_json()
    assert data["next_milestone"] is None
    assert data["amount_to_next"] == 0.0
    milestones = {m["threshold"]: m for m in data["milestones"]}
    assert all(m["reached"] for m in milestones.values())


def test_milestones_not_found(client, auth):
    r = client.get("/savings/goals/99999/milestones", headers=auth)
    assert r.status_code == 404


# ─── Auth & Isolation ──────────────────────────────────────────────────────


def test_goals_require_auth(client):
    assert client.get("/savings/goals").status_code == 401
    assert client.post("/savings/goals", json={"name": "X", "target_amount": 1}).status_code == 401


def test_users_cannot_see_others_goals(client, auth, goal):
    """Create another user and verify isolation."""
    client.post(
        "/auth/register",
        json={"email": "other@test.com", "password": "pass123456"},
    )
    r = client.post(
        "/auth/login",
        json={"email": "other@test.com", "password": "pass123456"},
    )
    other_auth = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    # Other user sees empty list
    r = client.get("/savings/goals", headers=other_auth)
    assert len(r.get_json()) == 0

    # Other user cannot access the goal
    r = client.get(f"/savings/goals/{goal['id']}", headers=other_auth)
    assert r.status_code == 404


def test_contribute_to_others_goal_fails(client, auth, goal):
    client.post("/auth/register", json={"email": "hacker@test.com", "password": "pass123"})
    r = client.post("/auth/login", json={"email": "hacker@test.com", "password": "pass123"})
    hacker_auth = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    r = client.post(
        f"/savings/goals/{goal['id']}/contribute",
        json={"amount": 100},
        headers=hacker_auth,
    )
    assert r.status_code == 404
