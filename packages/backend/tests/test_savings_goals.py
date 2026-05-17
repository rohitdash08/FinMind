"""Tests for savings goals and milestones API."""

import pytest
from datetime import date, timedelta
from app import create_app
from app.extensions import db as _db
from app.models import User, SavingsGoal, SavingsGoalStatus, SavingsMilestone


@pytest.fixture()
def app():
    app = create_app()
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        TESTING=True,
        JWT_SECRET_KEY="test-secret",
    )
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_header(client):
    # Register + login
    client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "Testpass1!",
    })
    resp = client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "Testpass1!",
    })
    token = resp.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestCreateGoal:
    def test_create_goal_success(self, client, auth_header):
        resp = client.post(
            "/api/savings-goals",
            json={"name": "Vacation Fund", "target_amount": 5000},
            headers=auth_header,
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "Vacation Fund"
        assert data["target_amount"] == 5000
        assert data["status"] == "ACTIVE"
        assert len(data["milestones"]) == 4  # default milestones

    def test_create_goal_missing_name(self, client, auth_header):
        resp = client.post(
            "/api/savings-goals",
            json={"target_amount": 1000},
            headers=auth_header,
        )
        assert resp.status_code == 400

    def test_create_goal_negative_target(self, client, auth_header):
        resp = client.post(
            "/api/savings-goals",
            json={"name": "Bad Goal", "target_amount": -100},
            headers=auth_header,
        )
        assert resp.status_code == 400

    def test_create_goal_with_deadline(self, client, auth_header):
        future = (date.today() + timedelta(days=365)).isoformat()
        resp = client.post(
            "/api/savings-goals",
            json={"name": "New Car", "target_amount": 20000, "deadline": future},
            headers=auth_header,
        )
        assert resp.status_code == 201
        assert resp.get_json()["deadline"] is not None


class TestListGoals:
    def test_list_goals_empty(self, client, auth_header):
        resp = client.get("/api/savings-goals", headers=auth_header)
        assert resp.status_code == 200
        assert resp.get_json()["goals"] == []

    def test_list_goals_with_filter(self, client, auth_header):
        # Create a goal
        client.post(
            "/api/savings-goals",
            json={"name": "Test", "target_amount": 100},
            headers=auth_header,
        )
        resp = client.get("/api/savings-goals?status=ACTIVE", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.get_json()["goals"]) == 1


class TestUpdateGoal:
    def test_add_funds(self, client, auth_header):
        # Create goal
        r = client.post(
            "/api/savings-goals",
            json={"name": "Save", "target_amount": 100},
            headers=auth_header,
        )
        goal_id = r.get_json()["id"]

        # Add funds
        resp = client.patch(
            f"/api/savings-goals/{goal_id}",
            json={"add_amount": 50},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.get_json()["current_amount"] == 50

    def test_auto_complete_at_100pct(self, client, auth_header):
        r = client.post(
            "/api/savings-goals",
            json={"name": "Quick Save", "target_amount": 100, "current_amount": 0},
            headers=auth_header,
        )
        goal_id = r.get_json()["id"]

        resp = client.patch(
            f"/api/savings-goals/{goal_id}",
            json={"add_amount": 100},
            headers=auth_header,
        )
        assert resp.get_json()["status"] == "COMPLETED"


class TestDeleteGoal:
    def test_cancel_goal(self, client, auth_header):
        r = client.post(
            "/api/savings-goals",
            json={"name": "Bye", "target_amount": 500},
            headers=auth_header,
        )
        goal_id = r.get_json()["id"]

        resp = client.delete(f"/api/savings-goals/{goal_id}", headers=auth_header)
        assert resp.status_code == 200
