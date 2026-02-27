"""Tests for spending velocity & burn rate analysis."""

import pytest
from datetime import date, timedelta
from app.services.burn_rate import (
    analyze_burn_rate, budget_runway, category_velocity, weekly_comparison,
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
def seed_expenses(app, user):
    with app.app_context():
        from app.extensions import db
        from app.models import Category, Expense
        food = Category(user_id=user, name="Food")
        transport = Category(user_id=user, name="Transport")
        db.session.add_all([food, transport])
        db.session.flush()
        today = date.today()
        for i in range(30):
            d = today - timedelta(days=i)
            # Accelerating: more recent = higher spend
            db.session.add(Expense(user_id=user, category_id=food.id, amount=50 + i * 2, description="food", date=d))
            db.session.add(Expense(user_id=user, category_id=transport.id, amount=20, description="bus", date=d))
        db.session.commit()
        return user


class TestBurnRate:
    def test_empty(self, app, user):
        with app.app_context():
            result = analyze_burn_rate(user)
            assert result["total_spent"] == 0
            assert result["velocity_trend"] == "insufficient_data"

    def test_with_data(self, app, seed_expenses):
        with app.app_context():
            result = analyze_burn_rate(seed_expenses)
            assert result["total_spent"] > 0
            assert result["daily_average"] > 0
            assert result["weekly_average"] > 0
            assert result["monthly_projected"] > 0
            assert result["velocity_trend"] in ("accelerating", "decelerating", "steady")

    def test_daily_breakdown(self, app, seed_expenses):
        with app.app_context():
            result = analyze_burn_rate(seed_expenses, days=7)
            assert len(result["daily_breakdown"]) == 8  # 7 days + today

    def test_custom_period(self, app, seed_expenses):
        with app.app_context():
            r7 = analyze_burn_rate(seed_expenses, days=7)
            r30 = analyze_burn_rate(seed_expenses, days=30)
            assert r30["total_spent"] >= r7["total_spent"]


class TestBudgetRunway:
    def test_no_spending(self, app, user):
        with app.app_context():
            result = budget_runway(user, 1000)
            assert result["status"] == "no_spending"
            assert result["days_remaining"] is None

    def test_healthy(self, app, seed_expenses):
        with app.app_context():
            result = budget_runway(seed_expenses, 100000)
            assert result["status"] == "healthy"
            assert result["days_remaining"] > 30

    def test_critical(self, app, seed_expenses):
        with app.app_context():
            result = budget_runway(seed_expenses, 100)
            assert result["status"] in ("critical", "warning")
            assert result["days_remaining"] < 14

    def test_has_projection(self, app, seed_expenses):
        with app.app_context():
            result = budget_runway(seed_expenses, 5000)
            assert result["projected_exhaustion"] is not None
            assert result["daily_burn"] > 0


class TestCategoryVelocity:
    def test_empty(self, app, user):
        with app.app_context():
            result = category_velocity(user)
            assert result == []

    def test_with_data(self, app, seed_expenses):
        with app.app_context():
            result = category_velocity(seed_expenses)
            assert len(result) == 2
            assert result[0]["total"] >= result[1]["total"]
            total_pct = sum(c["percentage"] for c in result)
            assert abs(total_pct - 100) < 1


class TestWeeklyComparison:
    def test_empty(self, app, user):
        with app.app_context():
            result = weekly_comparison(user)
            assert len(result["weeks"]) == 4

    def test_with_data(self, app, seed_expenses):
        with app.app_context():
            result = weekly_comparison(seed_expenses)
            assert len(result["weeks"]) == 4
            assert "overall_change_pct" in result
            for w in result["weeks"]:
                assert "total" in w
                assert "daily_avg" in w


class TestAPI:
    def test_burn_rate(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get("/burn-rate/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "total_spent" in resp.get_json()

    def test_runway(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get("/burn-rate/runway?budget=5000", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "days_remaining" in resp.get_json()

    def test_runway_missing_budget(self, app, user, token):
        client = app.test_client()
        resp = client.get("/burn-rate/runway", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

    def test_categories(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get("/burn-rate/categories", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_weekly(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get("/burn-rate/weekly", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "weeks" in resp.get_json()
