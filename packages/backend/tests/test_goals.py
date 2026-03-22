"""
Tests for /goals — Issue #133: Goal-based savings tracking & milestones
"""

import pytest
from app import create_app
from app.extensions import db as _db
from app.config import Settings


@pytest.fixture(scope="module")
def app():
    cfg = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="test-secret-tiktalik",
    )
    application = create_app(cfg)
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(client):
    client.post(
        "/auth/register", json={"email": "tiktalik@test.io", "password": "Test1234!"}
    )
    r = client.post(
        "/auth/login", json={"email": "tiktalik@test.io", "password": "Test1234!"}
    )
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── CREATE ────────────────────────────────────────────────────────────────────
def test_create_goal_returns_201(client, auth):
    r = client.post(
        "/goals",
        json={
            "name": "Emergency Fund",
            "target_amount": 5000,
            "currency": "USD",
            "icon": "🛡️",
        },
        headers=auth,
    )
    assert r.status_code == 201
    d = r.get_json()
    assert d["name"] == "Emergency Fund"
    assert d["target_amount"] == 5000.0
    assert d["current_amount"] == 0.0
    assert d["progress_pct"] == 0.0
    assert d["is_completed"] is False
    assert len(d["milestones"]) == 4


def test_create_goal_missing_name_returns_400(client, auth):
    r = client.post("/goals", json={"target_amount": 1000}, headers=auth)
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_create_goal_negative_amount_returns_400(client, auth):
    r = client.post("/goals", json={"name": "Bad", "target_amount": -50}, headers=auth)
    assert r.status_code == 400


def test_create_goal_invalid_deadline_returns_400(client, auth):
    r = client.post(
        "/goals",
        json={"name": "Test", "target_amount": 100, "deadline": "not-a-date"},
        headers=auth,
    )
    assert r.status_code == 400


# ── LIST / GET ────────────────────────────────────────────────────────────────
def test_list_goals_returns_list(client, auth):
    r = client.get("/goals", headers=auth)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_get_goal_by_id(client, auth):
    cr = client.post(
        "/goals", json={"name": "Vacation", "target_amount": 2000}, headers=auth
    )
    gid = cr.get_json()["id"]
    r = client.get(f"/goals/{gid}", headers=auth)
    assert r.status_code == 200
    assert r.get_json()["id"] == gid


# ── DEPOSIT & MILESTONES ──────────────────────────────────────────────────────
def test_deposit_updates_progress_and_milestone(client, auth):
    cr = client.post(
        "/goals", json={"name": "Car Fund", "target_amount": 1000}, headers=auth
    )
    gid = cr.get_json()["id"]

    r = client.post(f"/goals/{gid}/deposit", json={"amount": 250}, headers=auth)
    assert r.status_code == 200
    d = r.get_json()
    assert d["current_amount"] == 250.0
    assert d["progress_pct"] == 25.0

    ms25 = next(m for m in d["milestones"] if m["percentage"] == 25)
    ms50 = next(m for m in d["milestones"] if m["percentage"] == 50)
    assert ms25["reached"] is True
    assert ms50["reached"] is False


def test_deposit_zero_returns_400(client, auth):
    cr = client.post("/goals", json={"name": "X", "target_amount": 500}, headers=auth)
    gid = cr.get_json()["id"]
    r = client.post(f"/goals/{gid}/deposit", json={"amount": 0}, headers=auth)
    assert r.status_code == 400


def test_goal_marked_completed_at_100_pct(client, auth):
    cr = client.post(
        "/goals", json={"name": "Full", "target_amount": 300}, headers=auth
    )
    gid = cr.get_json()["id"]
    r = client.post(f"/goals/{gid}/deposit", json={"amount": 300}, headers=auth)
    d = r.get_json()
    assert d["is_completed"] is True
    assert d["progress_pct"] == 100.0
    ms100 = next(m for m in d["milestones"] if m["percentage"] == 100)
    assert ms100["reached"] is True


# ── UPDATE ────────────────────────────────────────────────────────────────────
def test_update_goal_name(client, auth):
    cr = client.post(
        "/goals", json={"name": "OldName", "target_amount": 200}, headers=auth
    )
    gid = cr.get_json()["id"]
    r = client.patch(f"/goals/{gid}", json={"name": "NewName"}, headers=auth)
    assert r.status_code == 200
    assert r.get_json()["name"] == "NewName"


# ── DELETE (soft) ─────────────────────────────────────────────────────────────
def test_delete_goal_soft_deletes(client, auth):
    cr = client.post(
        "/goals", json={"name": "TempGoal", "target_amount": 100}, headers=auth
    )
    gid = cr.get_json()["id"]
    r2 = client.delete(f"/goals/{gid}", headers=auth)
    assert r2.status_code == 200
    r3 = client.get(f"/goals/{gid}", headers=auth)
    assert r3.status_code == 404


def test_deleted_goal_excluded_from_list(client, auth):
    cr = client.post(
        "/goals", json={"name": "WillDelete", "target_amount": 50}, headers=auth
    )
    gid = cr.get_json()["id"]
    client.delete(f"/goals/{gid}", headers=auth)
    goals = client.get("/goals", headers=auth).get_json()
    assert not any(g["id"] == gid for g in goals)
