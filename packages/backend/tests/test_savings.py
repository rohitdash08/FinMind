"""Tests for goal-based savings tracking & milestones."""

import pytest
from app.services.savings import (
    SavingsGoal,
    SavingsMilestone,
    create_goal,
    get_goals,
    get_goal,
    contribute,
    update_goal,
    delete_goal,
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


class TestSavingsService:
    def test_create_goal(self, app, user):
        with app.app_context():
            g = create_goal(user, "Vacation", 5000, "USD", "2026-12-31")
            assert g["name"] == "Vacation"
            assert g["target_amount"] == 5000
            assert g["progress_pct"] == 0
            assert len(g["milestones"]) == 4
            assert g["deadline"] == "2026-12-31"

    def test_create_goal_invalid_amount(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                create_goal(user, "Bad", -100)

    def test_default_milestones(self, app, user):
        with app.app_context():
            g = create_goal(user, "Test", 1000)
            pcts = [m["target_pct"] for m in g["milestones"]]
            assert pcts == [25, 50, 75, 100]

    def test_list_goals(self, app, user):
        with app.app_context():
            create_goal(user, "A", 1000)
            create_goal(user, "B", 2000)
            goals = get_goals(user)
            assert len(goals) == 2

    def test_list_by_status(self, app, user):
        with app.app_context():
            create_goal(user, "Active", 1000)
            g2 = create_goal(user, "Done", 100)
            contribute(user, g2["id"], 100)
            active = get_goals(user, status="active")
            completed = get_goals(user, status="completed")
            assert len(active) == 1
            assert len(completed) == 1

    def test_get_goal(self, app, user):
        with app.app_context():
            created = create_goal(user, "Test", 500)
            fetched = get_goal(user, created["id"])
            assert fetched["name"] == "Test"

    def test_get_nonexistent(self, app, user):
        with app.app_context():
            assert get_goal(user, 9999) is None

    def test_contribute(self, app, user):
        with app.app_context():
            g = create_goal(user, "Fund", 1000)
            result = contribute(user, g["id"], 300)
            assert result["current_amount"] == 300
            assert result["progress_pct"] == 30.0
            assert len(result["newly_reached_milestones"]) == 1  # 25%

    def test_contribute_multiple_milestones(self, app, user):
        with app.app_context():
            g = create_goal(user, "Fund", 1000)
            result = contribute(user, g["id"], 800)
            assert result["progress_pct"] == 80.0
            reached = result["newly_reached_milestones"]
            assert len(reached) == 3  # 25%, 50%, 75%

    def test_contribute_completes_goal(self, app, user):
        with app.app_context():
            g = create_goal(user, "Fund", 100)
            result = contribute(user, g["id"], 100)
            assert result["status"] == "completed"
            assert result["progress_pct"] == 100.0
            assert len(result["newly_reached_milestones"]) == 4

    def test_contribute_invalid_amount(self, app, user):
        with app.app_context():
            g = create_goal(user, "Fund", 100)
            with pytest.raises(ValueError):
                contribute(user, g["id"], -50)

    def test_contribute_to_completed(self, app, user):
        with app.app_context():
            g = create_goal(user, "Fund", 100)
            contribute(user, g["id"], 100)
            result = contribute(user, g["id"], 50)
            assert result is None

    def test_update_goal(self, app, user):
        with app.app_context():
            g = create_goal(user, "Old", 1000)
            updated = update_goal(user, g["id"], name="New", target_amount=2000)
            assert updated["name"] == "New"
            assert updated["target_amount"] == 2000

    def test_delete_goal(self, app, user):
        with app.app_context():
            g = create_goal(user, "Del", 100)
            assert delete_goal(user, g["id"]) is True
            assert get_goal(user, g["id"]) is None

    def test_delete_nonexistent(self, app, user):
        with app.app_context():
            assert delete_goal(user, 9999) is False


class TestSavingsAPI:
    def test_create_endpoint(self, app, user, token):
        client = app.test_client()
        resp = client.post(
            "/savings/",
            json={"name": "Car", "target_amount": 20000},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.get_json()["name"] == "Car"
        assert len(resp.get_json()["milestones"]) == 4

    def test_create_missing_fields(self, app, user, token):
        client = app.test_client()
        resp = client.post(
            "/savings/",
            json={"name": "No Amount"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_contribute_endpoint(self, app, user, token):
        client = app.test_client()
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/savings/", json={"name": "Fund", "target_amount": 1000}, headers=h)
        gid = r.get_json()["id"]
        resp = client.post(f"/savings/{gid}/contribute", json={"amount": 500}, headers=h)
        assert resp.status_code == 200
        assert resp.get_json()["progress_pct"] == 50.0

    def test_list_endpoint(self, app, user, token):
        client = app.test_client()
        h = {"Authorization": f"Bearer {token}"}
        client.post("/savings/", json={"name": "A", "target_amount": 100}, headers=h)
        resp = client.get("/savings/", headers=h)
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_delete_endpoint(self, app, user, token):
        client = app.test_client()
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/savings/", json={"name": "Del", "target_amount": 100}, headers=h)
        gid = r.get_json()["id"]
        resp = client.delete(f"/savings/{gid}", headers=h)
        assert resp.status_code == 200
