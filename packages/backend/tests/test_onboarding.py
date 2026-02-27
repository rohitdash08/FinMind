"""Tests for smart onboarding financial setup wizard."""

import pytest
from app.services.onboarding import (
    get_progress, advance, skip_step, reset, get_suggestions, ONBOARDING_STEPS,
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


class TestProgress:
    def test_initial(self, app, user):
        with app.app_context():
            p = get_progress(user)
            assert p["current_step"] == 1
            assert p["completed"] is False
            assert p["total_steps"] == len(ONBOARDING_STEPS)

    def test_idempotent(self, app, user):
        with app.app_context():
            p1 = get_progress(user)
            p2 = get_progress(user)
            assert p1["id"] == p2["id"]


class TestAdvance:
    def test_basic(self, app, user):
        with app.app_context():
            get_progress(user)
            p = advance(user)
            assert p["current_step"] == 2

    def test_with_data(self, app, user):
        with app.app_context():
            get_progress(user)
            p = advance(user, {"currency": "USD"})
            assert p["current_step"] == 2

    def test_complete(self, app, user):
        with app.app_context():
            get_progress(user)
            for _ in range(len(ONBOARDING_STEPS)):
                p = advance(user)
            assert p["completed"] is True

    def test_already_completed(self, app, user):
        with app.app_context():
            get_progress(user)
            for _ in range(len(ONBOARDING_STEPS)):
                advance(user)
            p = advance(user)
            assert p["completed"] is True


class TestSkip:
    def test_skippable(self, app, user):
        with app.app_context():
            get_progress(user)
            advance(user)  # step 1 -> 2
            advance(user)  # step 2 -> 3
            p = skip_step(user)  # skip step 3
            assert p["current_step"] == 4
            assert 3 in p["skipped_steps"]

    def test_not_skippable(self, app, user):
        with app.app_context():
            get_progress(user)  # step 1 is not skippable
            with pytest.raises(ValueError):
                skip_step(user)

    def test_not_started(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                skip_step(user + 999)


class TestReset:
    def test_basic(self, app, user):
        with app.app_context():
            get_progress(user)
            advance(user)
            advance(user)
            p = reset(user)
            assert p["current_step"] == 1
            assert p["completed"] is False

    def test_not_started(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                reset(user + 999)


class TestSuggestions:
    def test_categories(self, app):
        with app.app_context():
            s = get_suggestions(3)
            assert "categories" in s
            assert len(s["categories"]) > 0

    def test_budgets(self, app):
        with app.app_context():
            s = get_suggestions(4)
            assert "suggested_budgets" in s

    def test_empty(self, app):
        with app.app_context():
            s = get_suggestions(1)
            assert s == {}


class TestAPI:
    def test_progress(self, app, user, token):
        client = app.test_client()
        resp = client.get("/onboarding/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_advance(self, app, user, token):
        client = app.test_client()
        client.get("/onboarding/", headers={"Authorization": f"Bearer {token}"})
        resp = client.post("/onboarding/advance", json={},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_skip(self, app, user, token):
        client = app.test_client()
        client.get("/onboarding/", headers={"Authorization": f"Bearer {token}"})
        # Advance to a skippable step (step 3)
        client.post("/onboarding/advance", json={}, headers={"Authorization": f"Bearer {token}"})
        client.post("/onboarding/advance", json={}, headers={"Authorization": f"Bearer {token}"})
        resp = client.post("/onboarding/skip", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_reset(self, app, user, token):
        client = app.test_client()
        client.get("/onboarding/", headers={"Authorization": f"Bearer {token}"})
        resp = client.post("/onboarding/reset", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_suggestions(self, app, user, token):
        client = app.test_client()
        resp = client.get("/onboarding/suggestions/3", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
