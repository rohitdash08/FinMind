"""Tests for financial goal tracking & milestones."""

import pytest
from datetime import date, timedelta
from app.services.financial_goals import (
    create_goal, get_goals, get_goal, update_goal, delete_goal,
    add_contribution, get_contributions, goal_projection,
)


@pytest.fixture
def app():
    from app import create_app
    from app.config import Settings
    settings = Settings()
    settings.database_url = "sqlite:///:memory:"
    app = create_app(settings)
    with app.app_context():
        from app.extensions import db
        db.create_all()
        yield app


@pytest.fixture
def user(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash
        u = User(email="test@example.com", password_hash=generate_password_hash("pass"))
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def token(app, user):
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(identity=str(user))


@pytest.fixture
def goal(app, user):
    with app.app_context():
        return create_goal(user, "Emergency Fund", 10000, category="emergency")


class TestGoalCRUD:
    def test_create(self, app, user):
        with app.app_context():
            g = create_goal(user, "Vacation", 5000, deadline="2026-12-31")
            assert g["name"] == "Vacation"
            assert g["target_amount"] == 5000
            assert g["status"] == "active"
            assert len(g["milestones"]) == 4

    def test_create_invalid(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                create_goal(user, "Bad", -100)

    def test_list(self, app, user, goal):
        with app.app_context():
            goals = get_goals(user)
            assert len(goals) == 1

    def test_list_by_status(self, app, user, goal):
        with app.app_context():
            assert len(get_goals(user, status="active")) == 1
            assert len(get_goals(user, status="completed")) == 0

    def test_get_one(self, app, user, goal):
        with app.app_context():
            g = get_goal(user, goal["id"])
            assert g["name"] == "Emergency Fund"

    def test_get_not_found(self, app, user):
        with app.app_context():
            assert get_goal(user, 9999) is None

    def test_update(self, app, user, goal):
        with app.app_context():
            g = update_goal(user, goal["id"], name="Updated Fund", target_amount=15000)
            assert g["name"] == "Updated Fund"
            assert g["target_amount"] == 15000

    def test_delete(self, app, user, goal):
        with app.app_context():
            assert delete_goal(user, goal["id"]) is True
            assert get_goal(user, goal["id"]) is None

    def test_delete_not_found(self, app, user):
        with app.app_context():
            assert delete_goal(user, 9999) is False


class TestContributions:
    def test_add(self, app, user, goal):
        with app.app_context():
            g = add_contribution(user, goal["id"], 2500, "First deposit")
            assert g["current_amount"] == 2500
            assert g["progress_pct"] == 25.0

    def test_milestone_reached(self, app, user, goal):
        with app.app_context():
            g = add_contribution(user, goal["id"], 5000)
            reached = [m for m in g["milestones"] if m["reached"]]
            assert len(reached) == 2  # 25% and 50%

    def test_auto_complete(self, app, user, goal):
        with app.app_context():
            g = add_contribution(user, goal["id"], 10000)
            assert g["status"] == "completed"
            reached = [m for m in g["milestones"] if m["reached"]]
            assert len(reached) == 4

    def test_invalid_amount(self, app, user, goal):
        with app.app_context():
            with pytest.raises(ValueError):
                add_contribution(user, goal["id"], -100)

    def test_list_contributions(self, app, user, goal):
        with app.app_context():
            add_contribution(user, goal["id"], 1000, "First")
            add_contribution(user, goal["id"], 2000, "Second")
            contribs = get_contributions(user, goal["id"])
            assert len(contribs) == 2


class TestProjection:
    def test_no_contributions(self, app, user, goal):
        with app.app_context():
            p = goal_projection(user, goal["id"])
            assert p["projected_completion"] is None

    def test_with_contributions(self, app, user, goal):
        with app.app_context():
            add_contribution(user, goal["id"], 1000)
            p = goal_projection(user, goal["id"])
            assert p["progress_pct"] == 10.0
            assert p["remaining"] == 9000

    def test_not_found(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                goal_projection(user, 9999)


class TestAPI:
    def test_create(self, app, user, token):
        client = app.test_client()
        resp = client.post("/goals/", json={"name": "Car", "target_amount": 20000},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_list(self, app, user, token, goal):
        client = app.test_client()
        resp = client.get("/goals/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_get_one(self, app, user, token, goal):
        client = app.test_client()
        resp = client.get(f"/goals/{goal['id']}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_update(self, app, user, token, goal):
        client = app.test_client()
        resp = client.put(f"/goals/{goal['id']}", json={"name": "New Name"},
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_delete(self, app, user, token, goal):
        client = app.test_client()
        resp = client.delete(f"/goals/{goal['id']}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_contribute(self, app, user, token, goal):
        client = app.test_client()
        resp = client.post(f"/goals/{goal['id']}/contributions", json={"amount": 500},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_projection(self, app, user, token, goal):
        client = app.test_client()
        resp = client.get(f"/goals/{goal['id']}/projection",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
