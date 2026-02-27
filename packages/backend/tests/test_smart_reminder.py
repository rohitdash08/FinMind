"""Tests for smart reminder timing optimization."""

import pytest
from datetime import date, timedelta
from app.services.smart_reminder import (
    get_preference, update_preference, analyze_payment_patterns,
    optimize_reminders, suggest_reminder_time, ReminderPreference,
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
def seed_data(app, user):
    """Create bills and expenses for pattern analysis."""
    with app.app_context():
        from app.extensions import db
        from app.models import Category, Expense, Bill

        cat = Category(user_id=user, name="Bills")
        db.session.add(cat)
        db.session.flush()

        # Bills
        db.session.add(Bill(user_id=user, name="Rent", amount=1500, due_date=15, category_id=cat.id))
        db.session.add(Bill(user_id=user, name="Electric", amount=100, due_date=20, category_id=cat.id))

        # Expenses spread across 3 months, heavier early month
        today = date.today()
        for i in range(90):
            d = today - timedelta(days=i)
            # More expenses early in month
            if d.day <= 10:
                for _ in range(3):
                    db.session.add(Expense(user_id=user, category_id=cat.id, amount=50, description="payment", date=d))
            else:
                db.session.add(Expense(user_id=user, category_id=cat.id, amount=30, description="misc", date=d))

        db.session.commit()
        return user


class TestPreference:
    def test_default(self, app, user):
        with app.app_context():
            pref = get_preference(user)
            assert pref["preferred_hour"] == 9
            assert pref["is_default"] is True

    def test_update(self, app, user):
        with app.app_context():
            pref = update_preference(user, hour=14, day_offset=5)
            assert pref["preferred_hour"] == 14
            assert pref["preferred_day_offset"] == 5
            assert pref["is_default"] is False

    def test_update_partial(self, app, user):
        with app.app_context():
            update_preference(user, hour=10)
            pref = update_preference(user, day_offset=2)
            assert pref["preferred_hour"] == 10
            assert pref["preferred_day_offset"] == 2

    def test_clamp_hour(self, app, user):
        with app.app_context():
            pref = update_preference(user, hour=25)
            assert pref["preferred_hour"] == 23

    def test_auto_optimize_toggle(self, app, user):
        with app.app_context():
            pref = update_preference(user, auto_optimize=False)
            assert pref["auto_optimize"] is False


class TestPatterns:
    def test_no_data(self, app, user):
        with app.app_context():
            result = analyze_payment_patterns(user)
            assert result["pattern"] == "no_data"

    def test_with_data(self, app, seed_data):
        with app.app_context():
            result = analyze_payment_patterns(seed_data)
            assert result["pattern"] in ("early_month", "mid_month", "late_month")
            assert result["bills_analyzed"] == 2
            assert result["expenses_analyzed"] > 0
            assert "peak_activity_day" in result

    def test_suggestions(self, app, seed_data):
        with app.app_context():
            result = analyze_payment_patterns(seed_data)
            assert len(result["suggestions"]) > 0
            for s in result["suggestions"]:
                assert "type" in s
                assert "description" in s
                assert "confidence" in s


class TestOptimize:
    def test_no_data(self, app, user):
        with app.app_context():
            result = optimize_reminders(user)
            assert result["optimized"] is False

    def test_with_data(self, app, seed_data):
        with app.app_context():
            result = optimize_reminders(seed_data)
            assert result["optimized"] is True
            assert "applied" in result

    def test_disabled(self, app, seed_data):
        with app.app_context():
            update_preference(seed_data, auto_optimize=False)
            result = optimize_reminders(seed_data)
            assert result["optimized"] is False
            assert result["reason"] == "auto_optimize_disabled"


class TestSuggestTime:
    def test_future_date(self, app, user):
        with app.app_context():
            due = date.today() + timedelta(days=10)
            result = suggest_reminder_time(user, due)
            assert result["due_date"] == due.isoformat()
            assert result["suggested_remind_date"] <= due.isoformat()

    def test_past_due(self, app, user):
        with app.app_context():
            due = date.today()
            result = suggest_reminder_time(user, due)
            assert result["suggested_remind_date"] == date.today().isoformat()


class TestAPI:
    def test_get_preference(self, app, user, token):
        client = app.test_client()
        resp = client.get("/smart-reminders/preference", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "preferred_hour" in resp.get_json()

    def test_update_preference(self, app, user, token):
        client = app.test_client()
        resp = client.put(
            "/smart-reminders/preference",
            json={"preferred_hour": 14},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_patterns(self, app, seed_data, token):
        client = app.test_client()
        resp = client.get("/smart-reminders/patterns", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_optimize(self, app, seed_data, token):
        client = app.test_client()
        resp = client.post("/smart-reminders/optimize", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_suggest(self, app, user, token):
        client = app.test_client()
        due = (date.today() + timedelta(days=10)).isoformat()
        resp = client.get(f"/smart-reminders/suggest?due_date={due}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_suggest_missing_date(self, app, user, token):
        client = app.test_client()
        resp = client.get("/smart-reminders/suggest", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400
