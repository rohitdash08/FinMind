"""Tests for the weekly financial digest feature (#121)."""
from datetime import date, timedelta

import pytest
from app.extensions import db
from app.models import Expense, User, Bill, Category


@pytest.fixture
def seed_user(app):
    with app.app_context():
        user = User(email="digest-test@test.com", password_hash="hash", preferred_currency="USD")
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def seed_data(app, seed_user):
    """Create sample expenses for the current week."""
    with app.app_context():
        user = seed_user
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        cat = Category(user_id=user.id, name="Food")
        db.session.add(cat)
        db.session.commit()

        expenses = [
            Expense(user_id=user.id, amount=50.00, expense_type="EXPENSE",
                    category_id=cat.id, notes="Groceries", spent_at=monday),
            Expense(user_id=user.id, amount=30.00, expense_type="EXPENSE",
                    category_id=cat.id, notes="Restaurant", spent_at=monday + timedelta(days=1)),
            Expense(user_id=user.id, amount=2000.00, expense_type="INCOME",
                    notes="Salary", spent_at=monday + timedelta(days=2)),
            Expense(user_id=user.id, amount=100.00, expense_type="EXPENSE",
                    notes="Utilities", spent_at=monday + timedelta(days=3)),
        ]
        for e in expenses:
            db.session.add(e)
        db.session.commit()
        yield user, cat


class TestWeeklyDigest:
    """Integration tests for weekly digest endpoints."""

    def test_weekly_digest_requires_user_id(self, client):
        resp = client.get("/api/digest/weekly")
        assert resp.status_code == 400
        assert "user_id" in resp.json["error"]

    def test_weekly_digest_returns_summary(self, client, seed_data):
        user, _ = seed_data
        resp = client.get(f"/api/digest/weekly?user_id={user.id}")
        assert resp.status_code == 200
        data = resp.json
        assert data["user_id"] == user.id
        assert "current_week" in data
        assert "previous_week" in data
        assert "insights" in data
        assert data["current_week"]["total_income"] == 2000.00
        assert data["current_week"]["total_spent"] == 180.00  # 50+30+100
        assert data["current_week"]["transaction_count"] == 4

    def test_weekly_digest_net_change(self, client, seed_data):
        user, _ = seed_data
        resp = client.get(f"/api/digest/weekly?user_id={user.id}")
        assert resp.status_code == 200
        data = resp.json
        # Income 2000 - spend 180 = +1820
        assert data["current_week"]["net_change"] == 1820.00

    def test_weekly_digest_contains_insights(self, client, seed_data):
        user, _ = seed_data
        resp = client.get(f"/api/digest/weekly?user_id={user.id}")
        assert resp.status_code == 200
        data = resp.json
        assert len(data["insights"]) > 0

    def test_weekly_history(self, client, seed_data):
        user, _ = seed_data
        resp = client.get(f"/api/digest/weekly/history?user_id={user.id}&weeks=2")
        assert resp.status_code == 200
        data = resp.json
        assert len(data["weeks"]) == 2
