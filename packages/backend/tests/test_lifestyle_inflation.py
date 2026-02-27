"""Tests for lifestyle inflation detection."""

import pytest
from datetime import date, timedelta
from app.services.lifestyle_inflation import detect_inflation, _compute_trend, _generate_insights


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
def inflating_user(app, user):
    """User with increasing spending over 6 months."""
    with app.app_context():
        from app.extensions import db
        from app.models import Category, Expense
        cat = Category(user_id=user, name="Dining")
        db.session.add(cat)
        db.session.flush()
        today = date.today()
        for i in range(180):
            d = today - timedelta(days=i)
            months_ago = i // 30
            amount = 50 + (5 - months_ago) * 30  # more recent = higher
            db.session.add(Expense(
                user_id=user, category_id=cat.id,
                amount=max(amount, 10), description="dining", date=d,
            ))
        db.session.commit()
        return user


class TestComputeTrend:
    def test_increasing(self):
        t = _compute_trend([100, 110, 120, 150, 180, 200])
        assert t["direction"] == "increasing"
        assert t["growth_rate"] > 0

    def test_decreasing(self):
        t = _compute_trend([200, 180, 150, 120, 100, 80])
        assert t["direction"] == "decreasing"
        assert t["growth_rate"] < 0

    def test_stable(self):
        t = _compute_trend([100, 101, 99, 100, 102, 100])
        assert t["direction"] == "stable"

    def test_single_value(self):
        t = _compute_trend([100])
        assert t["direction"] == "insufficient_data"

    def test_from_zero(self):
        t = _compute_trend([0, 0, 50, 100])
        assert t["growth_rate"] == 100.0


class TestGenerateInsights:
    def test_high_inflation(self):
        overall = {"direction": "increasing", "growth_rate": 35}
        insights = _generate_insights(overall, [], [])
        assert any("Significant" in i for i in insights)

    def test_moderate_inflation(self):
        overall = {"direction": "increasing", "growth_rate": 20}
        insights = _generate_insights(overall, [], [])
        assert any("Moderate" in i for i in insights)

    def test_decreasing(self):
        overall = {"direction": "decreasing", "growth_rate": -15}
        insights = _generate_insights(overall, [], [])
        assert any("decreased" in i for i in insights)

    def test_stable(self):
        overall = {"direction": "stable", "growth_rate": 2}
        insights = _generate_insights(overall, [], [])
        assert any("stable" in i for i in insights)

    def test_category_surge(self):
        overall = {"direction": "increasing", "growth_rate": 10}
        cats = [{"category": "Dining", "growth_rate": 80, "first_month": 100, "last_month": 180}]
        insights = _generate_insights(overall, cats, [])
        assert any("Dining" in i for i in insights)


class TestDetectInflation:
    def test_empty_user(self, app, user):
        with app.app_context():
            result = detect_inflation(user)
            assert result["inflation_detected"] is False
            assert result["overall_trend"] == "insufficient_data"

    def test_with_data(self, app, inflating_user):
        with app.app_context():
            result = detect_inflation(inflating_user)
            assert "monthly_totals" in result
            assert len(result["monthly_totals"]) > 0
            assert "insights" in result

    def test_structure(self, app, inflating_user):
        with app.app_context():
            result = detect_inflation(inflating_user)
            assert "inflation_detected" in result
            assert "overall_trend" in result
            assert "category_trends" in result
            assert isinstance(result["insights"], list)


class TestAPI:
    def test_endpoint(self, app, inflating_user, token):
        client = app.test_client()
        resp = client.get(
            "/lifestyle-inflation/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "inflation_detected" in data

    def test_custom_months(self, app, inflating_user, token):
        client = app.test_client()
        resp = client.get(
            "/lifestyle-inflation/?months=3",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_unauthorized(self, app):
        client = app.test_client()
        resp = client.get("/lifestyle-inflation/")
        assert resp.status_code == 401
