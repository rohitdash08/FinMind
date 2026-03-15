"""Tests for Smart Weekly Digest feature.

Covers:
- Digest generation with no data
- Digest with seeded transactions showing trends
- Week-over-week comparison
- Top categories ranking
- Largest transactions list
- Upcoming bills detection
- Insight generation (spending spike, positive flow, no activity)
- Date anchor parameter
- History endpoint
- Auth requirements
"""

import pytest
from datetime import date, timedelta
from app.extensions import db
from app.models import User, Category, Expense, Bill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_login(client, email="digest@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_expenses(app, user_id, days_ago_amounts, expense_type="EXPENSE",
                   category_name="Food"):
    """Seed expenses at various days ago with given amounts.

    days_ago_amounts: list of (days_ago, amount) tuples
    """
    with app.app_context():
        cat = Category.query.filter_by(
            user_id=user_id, name=category_name
        ).first()
        if not cat:
            cat = Category(user_id=user_id, name=category_name)
            db.session.add(cat)
            db.session.flush()

        today = date.today()
        for days_ago, amount in days_ago_amounts:
            db.session.add(Expense(
                user_id=user_id,
                category_id=cat.id,
                amount=amount,
                expense_type=expense_type,
                notes=f"Test expense {days_ago}d ago",
                spent_at=today - timedelta(days=days_ago),
            ))
        db.session.commit()
        return cat.id


def _seed_bill(app, user_id, name, amount, days_until_due):
    with app.app_context():
        db.session.add(Bill(
            user_id=user_id,
            name=name,
            amount=amount,
            next_due_date=date.today() + timedelta(days=days_until_due),
            cadence="MONTHLY",
        ))
        db.session.commit()


def _get_user_id(app, email="digest@test.com"):
    with app.app_context():
        return User.query.filter_by(email=email).first().id


# ---------------------------------------------------------------------------
# Digest endpoint tests
# ---------------------------------------------------------------------------

class TestWeeklyDigest:
    def test_empty_digest(self, app_fixture, client):
        """Digest with no data should return zeros and 'No Activity' insight."""
        hdr = _register_and_login(client)
        r = client.get("/digest/weekly", headers=hdr)
        assert r.status_code == 200
        d = r.get_json()["digest"]

        assert d["summary"]["total_income"] == 0
        assert d["summary"]["total_expenses"] == 0
        assert d["summary"]["net_savings"] == 0
        assert d["summary"]["transaction_count"] == 0
        insight_types = [i["type"] for i in d["insights"]]
        assert "info" in insight_types

    def test_digest_with_expenses(self, app_fixture, client):
        """Digest reflects seeded expenses correctly."""
        hdr = _register_and_login(client)
        uid = _get_user_id(app_fixture)

        # Seed current week expenses (within 6 days ago)
        _seed_expenses(app_fixture, uid, [
            (0, 100),  # today
            (1, 50),   # yesterday
            (3, 200),  # 3 days ago
        ])
        # Seed income
        _seed_expenses(app_fixture, uid, [
            (0, 500),
        ], expense_type="INCOME")

        r = client.get("/digest/weekly", headers=hdr)
        assert r.status_code == 200
        d = r.get_json()["digest"]

        assert d["summary"]["total_expenses"] == 350.0
        assert d["summary"]["total_income"] == 500.0
        assert d["summary"]["net_savings"] == 150.0
        assert d["summary"]["transaction_count"] == 4

    def test_week_over_week_comparison(self, app_fixture, client):
        """Previous week data populated for comparison."""
        hdr = _register_and_login(client)
        uid = _get_user_id(app_fixture)

        # Current week: $300 expenses
        _seed_expenses(app_fixture, uid, [(0, 300)])
        # Previous week: $100 expenses
        _seed_expenses(app_fixture, uid, [(8, 100)])

        r = client.get("/digest/weekly", headers=hdr)
        d = r.get_json()["digest"]

        assert d["summary"]["total_expenses"] == 300.0
        assert d["summary"]["previous_week"]["total_expenses"] == 100.0
        assert d["summary"]["change"]["expenses_pct"] == 200.0  # +200%

    def test_top_categories(self, app_fixture, client):
        """Categories ranked by spending amount."""
        hdr = _register_and_login(client)
        uid = _get_user_id(app_fixture)

        _seed_expenses(app_fixture, uid, [(0, 500)], category_name="Rent")
        _seed_expenses(app_fixture, uid, [(0, 100)], category_name="Food")
        _seed_expenses(app_fixture, uid, [(0, 50)], category_name="Transport")

        r = client.get("/digest/weekly", headers=hdr)
        cats = r.get_json()["digest"]["top_categories"]

        assert len(cats) == 3
        assert cats[0]["category_name"] == "Rent"
        assert cats[0]["amount"] == 500.0
        assert cats[0]["share_pct"] > 70  # 500/650 ≈ 76.9%

    def test_largest_transactions(self, app_fixture, client):
        """Top transactions sorted by amount descending."""
        hdr = _register_and_login(client)
        uid = _get_user_id(app_fixture)

        _seed_expenses(app_fixture, uid, [
            (0, 10), (1, 999), (2, 50), (3, 500),
        ])

        r = client.get("/digest/weekly", headers=hdr)
        txns = r.get_json()["digest"]["largest_transactions"]

        assert txns[0]["amount"] == 999.0
        assert txns[1]["amount"] == 500.0

    def test_upcoming_bills(self, app_fixture, client):
        """Bills due within 7 days appear in digest."""
        hdr = _register_and_login(client)
        uid = _get_user_id(app_fixture)

        _seed_bill(app_fixture, uid, "Electricity", 100, 3)
        _seed_bill(app_fixture, uid, "Gym", 50, 5)
        _seed_bill(app_fixture, uid, "Insurance", 200, 30)  # too far

        r = client.get("/digest/weekly", headers=hdr)
        bills = r.get_json()["digest"]["upcoming_bills"]

        assert len(bills) == 2
        names = [b["name"] for b in bills]
        assert "Electricity" in names
        assert "Gym" in names
        assert "Insurance" not in names

    def test_spending_spike_insight(self, app_fixture, client):
        """Spending spike insight triggers when expenses up >20%."""
        hdr = _register_and_login(client)
        uid = _get_user_id(app_fixture)

        # Previous week: $100
        _seed_expenses(app_fixture, uid, [(8, 100)])
        # Current week: $200 (100% increase)
        _seed_expenses(app_fixture, uid, [(0, 200)])

        r = client.get("/digest/weekly", headers=hdr)
        insights = r.get_json()["digest"]["insights"]
        titles = [i["title"] for i in insights]
        assert "Spending Spike" in titles

    def test_positive_cash_flow_insight(self, app_fixture, client):
        """Positive cash flow insight when income > expenses."""
        hdr = _register_and_login(client)
        uid = _get_user_id(app_fixture)

        _seed_expenses(app_fixture, uid, [(0, 1000)], expense_type="INCOME")
        _seed_expenses(app_fixture, uid, [(0, 200)])

        r = client.get("/digest/weekly", headers=hdr)
        insights = r.get_json()["digest"]["insights"]
        titles = [i["title"] for i in insights]
        assert "Positive Cash Flow" in titles

    def test_date_anchor_parameter(self, app_fixture, client):
        """Can specify a custom anchor date to generate historical digest."""
        hdr = _register_and_login(client)
        anchor = (date.today() - timedelta(days=14)).isoformat()

        r = client.get(f"/digest/weekly?date={anchor}", headers=hdr)
        assert r.status_code == 200
        d = r.get_json()["digest"]
        assert d["period"]["end"] == anchor

    def test_invalid_date_rejected(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.get("/digest/weekly?date=not-a-date", headers=hdr)
        assert r.status_code == 400

    def test_requires_auth(self, client):
        r = client.get("/digest/weekly")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# History endpoint tests
# ---------------------------------------------------------------------------

class TestWeeklyHistory:
    def test_history_returns_multiple_weeks(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.get("/digest/weekly/history?weeks=3", headers=hdr)
        assert r.status_code == 200
        history = r.get_json()["history"]
        assert len(history) == 3
        # Each entry has period and summary
        for entry in history:
            assert "period" in entry
            assert "summary" in entry
            assert "insight_count" in entry

    def test_history_default_4_weeks(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.get("/digest/weekly/history", headers=hdr)
        assert r.status_code == 200
        assert len(r.get_json()["history"]) == 4

    def test_history_requires_auth(self, client):
        r = client.get("/digest/weekly/history")
        assert r.status_code == 401
