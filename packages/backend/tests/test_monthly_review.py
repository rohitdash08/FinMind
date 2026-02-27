"""Tests for guided monthly financial review."""

import pytest
from app.services.monthly_review import (
    start_review, get_review, get_step_data, advance_step,
    set_action_items, list_reviews, REVIEW_STEPS,
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
def review(app, user):
    with app.app_context():
        return start_review(user, 2026, 1)


class TestReviewCRUD:
    def test_start(self, app, user):
        with app.app_context():
            r = start_review(user, 2026, 2)
            assert r["year"] == 2026
            assert r["month"] == 2
            assert r["current_step"] == 1
            assert r["completed"] is False

    def test_start_idempotent(self, app, user, review):
        with app.app_context():
            r2 = start_review(user, 2026, 1)
            assert r2["id"] == review["id"]

    def test_get(self, app, user, review):
        with app.app_context():
            r = get_review(user, 2026, 1)
            assert r is not None
            assert r["year"] == 2026

    def test_get_not_found(self, app, user):
        with app.app_context():
            assert get_review(user, 2025, 1) is None

    def test_list(self, app, user, review):
        with app.app_context():
            reviews = list_reviews(user)
            assert len(reviews) == 1


class TestSteps:
    def test_step_1(self, app, user, review):
        with app.app_context():
            data = get_step_data(user, 2026, 1, 1)
            assert data["step"]["name"] == "spending_overview"
            assert "total_spent" in data["content"]

    def test_step_2(self, app, user, review):
        with app.app_context():
            data = get_step_data(user, 2026, 1, 2)
            assert data["step"]["name"] == "category_breakdown"

    def test_step_3(self, app, user, review):
        with app.app_context():
            data = get_step_data(user, 2026, 1, 3)
            assert "current_month" in data["content"]

    def test_step_4(self, app, user, review):
        with app.app_context():
            data = get_step_data(user, 2026, 1, 4)
            assert data["step"]["name"] == "top_expenses"

    def test_step_5(self, app, user, review):
        with app.app_context():
            data = get_step_data(user, 2026, 1, 5)
            assert data["step"]["name"] == "action_items"

    def test_invalid_step(self, app, user, review):
        with app.app_context():
            with pytest.raises(ValueError):
                get_step_data(user, 2026, 1, 99)

    def test_advance(self, app, user, review):
        with app.app_context():
            r = advance_step(user, 2026, 1, "Looks good")
            assert r["current_step"] == 2
            assert "Looks good" in r["notes"]

    def test_advance_to_completion(self, app, user, review):
        with app.app_context():
            for _ in range(len(REVIEW_STEPS)):
                r = advance_step(user, 2026, 1)
            assert r["completed"] is True

    def test_advance_no_review(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                advance_step(user, 2025, 1)


class TestActionItems:
    def test_set(self, app, user, review):
        with app.app_context():
            r = set_action_items(user, 2026, 1, "Reduce dining out")
            assert r["action_items"] == "Reduce dining out"

    def test_not_found(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                set_action_items(user, 2025, 1, "X")


class TestAPI:
    def test_start(self, app, user, token):
        client = app.test_client()
        resp = client.post("/reviews/start", json={"year": 2026, "month": 3},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_list(self, app, user, token, review):
        client = app.test_client()
        resp = client.get("/reviews/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_get(self, app, user, token, review):
        client = app.test_client()
        resp = client.get("/reviews/2026/1", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_step(self, app, user, token, review):
        client = app.test_client()
        resp = client.get("/reviews/2026/1/step/1", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_advance(self, app, user, token, review):
        client = app.test_client()
        resp = client.post("/reviews/2026/1/advance", json={"notes": "ok"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_actions(self, app, user, token, review):
        client = app.test_client()
        resp = client.put("/reviews/2026/1/actions", json={"items": "Save more"},
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
