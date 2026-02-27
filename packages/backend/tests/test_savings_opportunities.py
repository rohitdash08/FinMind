"""Tests for savings opportunity detection engine."""

import pytest
from datetime import date, timedelta
from app.services.savings_opportunities import (
    detect_opportunities,
    _detect_recurring_spikes,
    _detect_high_frequency_small,
    _detect_category_concentration,
    _detect_weekend_spending,
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
    """Create varied expenses for detection testing."""
    with app.app_context():
        from app.extensions import db
        from app.models import Category, Expense

        food = Category(user_id=user, name="Food")
        transport = Category(user_id=user, name="Transport")
        entertainment = Category(user_id=user, name="Entertainment")
        db.session.add_all([food, transport, entertainment])
        db.session.flush()

        today = date.today()
        expenses = []

        # Food: normal spending across months
        for i in range(60):
            d = today - timedelta(days=i)
            expenses.append(Expense(
                user_id=user, category_id=food.id,
                amount=30 + (i % 10), description="food", date=d,
            ))

        # Transport: spike in current month
        for i in range(10):
            expenses.append(Expense(
                user_id=user, category_id=transport.id,
                amount=500, description="taxi", date=today - timedelta(days=i),
            ))
        for i in range(30, 60):
            expenses.append(Expense(
                user_id=user, category_id=transport.id,
                amount=50, description="bus", date=today - timedelta(days=i),
            ))

        # Entertainment: weekend heavy
        for i in range(90):
            d = today - timedelta(days=i)
            if d.weekday() >= 5:
                expenses.append(Expense(
                    user_id=user, category_id=entertainment.id,
                    amount=200, description="weekend fun", date=d,
                ))
            else:
                expenses.append(Expense(
                    user_id=user, category_id=entertainment.id,
                    amount=20, description="weekday", date=d,
                ))

        db.session.add_all(expenses)
        db.session.commit()
        return user


class TestDetectOpportunities:
    def test_empty_user(self, app, user):
        with app.app_context():
            result = detect_opportunities(user)
            assert result["opportunities"] == []
            assert result["potential_monthly_savings"] == 0

    def test_with_data(self, app, seed_expenses):
        with app.app_context():
            result = detect_opportunities(seed_expenses)
            assert result["total_expenses_analyzed"] > 0
            assert isinstance(result["opportunities"], list)
            assert result["potential_monthly_savings"] >= 0

    def test_sorted_by_savings(self, app, seed_expenses):
        with app.app_context():
            result = detect_opportunities(seed_expenses)
            opps = result["opportunities"]
            if len(opps) >= 2:
                assert opps[0]["estimated_monthly_savings"] >= opps[1]["estimated_monthly_savings"]

    def test_opportunity_structure(self, app, seed_expenses):
        with app.app_context():
            result = detect_opportunities(seed_expenses)
            for opp in result["opportunities"]:
                assert "type" in opp
                assert "category" in opp
                assert "description" in opp
                assert "estimated_monthly_savings" in opp
                assert "confidence" in opp
                assert opp["confidence"] in ("low", "medium", "high")


class TestDetectors:
    def test_recurring_spikes_empty(self):
        assert _detect_recurring_spikes([]) == []

    def test_high_frequency_empty(self):
        assert _detect_high_frequency_small([]) == []

    def test_category_concentration_empty(self):
        assert _detect_category_concentration([]) == []

    def test_weekend_spending_empty(self):
        assert _detect_weekend_spending([]) == []


class TestAPI:
    def test_endpoint(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get(
            "/savings-opportunities/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "opportunities" in data
        assert "potential_monthly_savings" in data

    def test_custom_months(self, app, seed_expenses, token):
        client = app.test_client()
        resp = client.get(
            "/savings-opportunities/?months=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_unauthorized(self, app):
        client = app.test_client()
        resp = client.get("/savings-opportunities/")
        assert resp.status_code == 401
