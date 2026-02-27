"""Tests for the weekly digest feature."""

import pytest
from datetime import date, timedelta
from app.services.digest import (
    _week_bounds,
    _trend,
    _category_totals,
    _top_categories,
    _category_trends,
    _generate_insights,
    weekly_digest,
)


class TestWeekBounds:
    def test_monday_input(self):
        start, end = _week_bounds(date(2026, 2, 23))  # Monday
        assert start == date(2026, 2, 23)
        assert end == date(2026, 3, 1)

    def test_wednesday_input(self):
        start, end = _week_bounds(date(2026, 2, 25))  # Wednesday
        assert start == date(2026, 2, 23)
        assert end == date(2026, 3, 1)

    def test_sunday_input(self):
        start, end = _week_bounds(date(2026, 3, 1))  # Sunday
        assert start == date(2026, 2, 23)
        assert end == date(2026, 3, 1)


class TestTrend:
    def test_increase(self):
        t = _trend(150, 100)
        assert t["direction"] == "up"
        assert t["change_pct"] == 50.0

    def test_decrease(self):
        t = _trend(80, 100)
        assert t["direction"] == "down"
        assert t["change_pct"] == -20.0

    def test_flat(self):
        t = _trend(100, 100)
        assert t["direction"] == "flat"
        assert t["change_pct"] == 0.0

    def test_from_zero(self):
        t = _trend(50, 0)
        assert t["direction"] == "up"
        assert t["change_pct"] == 100.0

    def test_both_zero(self):
        t = _trend(0, 0)
        assert t["direction"] == "flat"
        assert t["change_pct"] == 0.0


class TestTopCategories:
    def test_returns_top_n(self):
        totals = {"Food": 300, "Transport": 150, "Entertainment": 200, "Bills": 100}
        top = _top_categories(totals, n=2)
        assert len(top) == 2
        assert top[0]["category"] == "Food"
        assert top[1]["category"] == "Entertainment"

    def test_empty(self):
        assert _top_categories({}) == []


class TestCategoryTrends:
    def test_basic_trends(self):
        current = {"Food": 200, "Transport": 50}
        previous = {"Food": 100, "Transport": 100}
        trends = _category_trends(current, previous)
        food = next(t for t in trends if t["category"] == "Food")
        assert food["direction"] == "up"
        assert food["change_pct"] == 100.0
        transport = next(t for t in trends if t["category"] == "Transport")
        assert transport["direction"] == "down"

    def test_new_category(self):
        current = {"NewCat": 50}
        previous = {}
        trends = _category_trends(current, previous)
        assert len(trends) == 1
        assert trends[0]["change_pct"] == 100.0

    def test_removed_category(self):
        current = {}
        previous = {"OldCat": 100}
        trends = _category_trends(current, previous)
        assert len(trends) == 1
        assert trends[0]["direction"] == "down"


class TestGenerateInsights:
    def test_high_increase(self):
        trend = {"direction": "up", "change_pct": 30}
        insights = _generate_insights(trend, [])
        assert any("increased" in i for i in insights)

    def test_decrease(self):
        trend = {"direction": "down", "change_pct": -15}
        insights = _generate_insights(trend, [])
        assert any("decreased" in i for i in insights)

    def test_stable(self):
        trend = {"direction": "flat", "change_pct": 0}
        insights = _generate_insights(trend, [])
        assert any("stable" in i for i in insights)

    def test_category_surge(self):
        trend = {"direction": "up", "change_pct": 10}
        cat_trends = [
            {
                "category": "Food",
                "current_amount": 300,
                "previous_amount": 100,
                "change_pct": 200.0,
                "direction": "up",
            }
        ]
        insights = _generate_insights(trend, cat_trends)
        assert any("Food" in i for i in insights)


class TestWeeklyDigestIntegration:
    """Integration tests using the Flask test app."""

    @pytest.fixture
    def app(self):
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
    def seed_data(self, app):
        with app.app_context():
            from app.extensions import db
            from app.models import User, Category, Expense
            from werkzeug.security import generate_password_hash

            user = User(
                email="test@example.com",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            cat_food = Category(user_id=user.id, name="Food")
            cat_transport = Category(user_id=user.id, name="Transport")
            db.session.add_all([cat_food, cat_transport])
            db.session.flush()

            today = date.today()
            monday = today - timedelta(days=today.weekday())

            # Current week expenses
            db.session.add(
                Expense(
                    user_id=user.id,
                    category_id=cat_food.id,
                    amount=150.0,
                    description="Groceries",
                    date=monday,
                )
            )
            db.session.add(
                Expense(
                    user_id=user.id,
                    category_id=cat_transport.id,
                    amount=50.0,
                    description="Bus",
                    date=monday + timedelta(days=1),
                )
            )

            # Previous week expenses
            prev_monday = monday - timedelta(days=7)
            db.session.add(
                Expense(
                    user_id=user.id,
                    category_id=cat_food.id,
                    amount=100.0,
                    description="Groceries last week",
                    date=prev_monday,
                )
            )
            db.session.add(
                Expense(
                    user_id=user.id,
                    category_id=cat_transport.id,
                    amount=80.0,
                    description="Taxi",
                    date=prev_monday + timedelta(days=2),
                )
            )

            db.session.commit()
            return user.id

    def test_digest_structure(self, app, seed_data):
        with app.app_context():
            result = weekly_digest(seed_data)
            assert "week" in result
            assert "previous_week" in result
            assert "current_total" in result
            assert "previous_total" in result
            assert "total_trend" in result
            assert "top_categories" in result
            assert "category_trends" in result
            assert "insights" in result

    def test_digest_totals(self, app, seed_data):
        with app.app_context():
            result = weekly_digest(seed_data)
            assert result["current_total"] == 200.0
            assert result["previous_total"] == 180.0

    def test_digest_trend_direction(self, app, seed_data):
        with app.app_context():
            result = weekly_digest(seed_data)
            assert result["total_trend"]["direction"] == "up"

    def test_digest_top_categories(self, app, seed_data):
        with app.app_context():
            result = weekly_digest(seed_data)
            assert len(result["top_categories"]) == 2
            assert result["top_categories"][0]["category"] == "Food"

    def test_digest_empty_user(self, app):
        with app.app_context():
            from app.extensions import db
            from app.models import User
            from werkzeug.security import generate_password_hash

            user = User(
                email="empty@example.com",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()

            result = weekly_digest(user.id)
            assert result["current_total"] == 0
            assert result["previous_total"] == 0
            assert result["total_trend"]["direction"] == "flat"

    def test_digest_api_endpoint(self, app, seed_data):
        client = app.test_client()
        from flask_jwt_extended import create_access_token

        with app.app_context():
            token = create_access_token(identity=str(seed_data))

        resp = client.get(
            "/digest/weekly-digest",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "insights" in data
        assert data["current_total"] == 200.0
