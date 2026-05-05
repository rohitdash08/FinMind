"""
Tests for the Weekly Smart Digest feature.

Covers:
- Digest generation with various data scenarios
- API endpoint responses
- Edge cases (no data, single transaction, etc.)
- Anomaly detection
- Narrative generation (heuristic mode)
"""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
from app.models import Bill, Category, Expense, User


class TestSettings(Settings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/15"
    jwt_secret: str = "test-secret-with-32-plus-chars-1234567890"
    gemini_api_key: str | None = None


@pytest.fixture()
def app():
    settings = TestSettings()
    application = create_app(settings)
    application.config["TESTING"] = True
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_header(client):
    client.post("/auth/register", json={"email": "test@x.com", "password": "pass1234"})
    r = client.post("/auth/login", json={"email": "test@x.com", "password": "pass1234"})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def user_with_data(app, auth_header):
    """Create a user with 2 weeks of expense data + categories + bills."""
    with app.app_context():
        user = db.session.query(User).filter_by(email="test@x.com").first()
        uid = user.id

        # Categories
        groceries = Category(user_id=uid, name="Groceries")
        transport = Category(user_id=uid, name="Transport")
        dining = Category(user_id=uid, name="Dining Out")
        db.session.add_all([groceries, transport, dining])
        db.session.flush()

        # Reference: today's previous full week (Mon-Sun)
        today = date.today()
        last_monday = today - timedelta(days=today.weekday() + 7)

        # CURRENT WEEK expenses (last complete week)
        expenses_current = [
            Expense(
                user_id=uid,
                category_id=groceries.id,
                amount=Decimal("45.00"),
                spent_at=last_monday,
                expense_type="EXPENSE",
                notes="Weekly grocery run",
            ),
            Expense(
                user_id=uid,
                category_id=groceries.id,
                amount=Decimal("22.50"),
                spent_at=last_monday + timedelta(days=3),
                expense_type="EXPENSE",
                notes="Mid-week top up",
            ),
            Expense(
                user_id=uid,
                category_id=transport.id,
                amount=Decimal("30.00"),
                spent_at=last_monday + timedelta(days=1),
                expense_type="EXPENSE",
                notes="Uber rides",
            ),
            Expense(
                user_id=uid,
                category_id=dining.id,
                amount=Decimal("85.00"),
                spent_at=last_monday + timedelta(days=5),
                expense_type="EXPENSE",
                notes="Birthday dinner",
            ),
            # Income
            Expense(
                user_id=uid,
                category_id=None,
                amount=Decimal("500.00"),
                spent_at=last_monday + timedelta(days=4),
                expense_type="INCOME",
                notes="Freelance payment",
            ),
        ]

        # PREVIOUS WEEK expenses
        prev_monday = last_monday - timedelta(days=7)
        expenses_prev = [
            Expense(
                user_id=uid,
                category_id=groceries.id,
                amount=Decimal("40.00"),
                spent_at=prev_monday,
                expense_type="EXPENSE",
                notes="Groceries",
            ),
            Expense(
                user_id=uid,
                category_id=transport.id,
                amount=Decimal("60.00"),
                spent_at=prev_monday + timedelta(days=2),
                expense_type="EXPENSE",
                notes="Train pass",
            ),
            Expense(
                user_id=uid,
                category_id=dining.id,
                amount=Decimal("25.00"),
                spent_at=prev_monday + timedelta(days=4),
                expense_type="EXPENSE",
                notes="Quick lunch",
            ),
        ]

        # Upcoming bill
        bill = Bill(
            user_id=uid,
            name="Netflix",
            amount=Decimal("15.99"),
            next_due_date=date.today() + timedelta(days=3),
            cadence="MONTHLY",
            active=True,
        )

        db.session.add_all(expenses_current + expenses_prev + [bill])
        db.session.commit()

    return uid


# ─── Unit Tests: Digest Service ──────────────────────────────────


class TestDigestService:
    def test_generate_digest_with_data(self, app, user_with_data):
        from app.services.digest import generate_digest

        with app.app_context():
            digest = generate_digest(user_with_data)

        assert "period" in digest
        assert "summary" in digest
        assert "comparison" in digest
        assert "by_category" in digest
        assert "daily_breakdown" in digest
        assert "anomalies" in digest
        assert "upcoming_bills" in digest
        assert "narrative" in digest
        assert "top_expense" in digest

    def test_summary_totals(self, app, user_with_data):
        from app.services.digest import generate_digest

        with app.app_context():
            digest = generate_digest(user_with_data)

        s = digest["summary"]
        # Current week: 45 + 22.5 + 30 + 85 = 182.50
        assert s["total_spent"] == 182.50
        assert s["total_income"] == 500.00
        assert s["net_flow"] == 317.50
        assert s["transaction_count"] == 4

    def test_comparison_with_previous_week(self, app, user_with_data):
        from app.services.digest import generate_digest

        with app.app_context():
            digest = generate_digest(user_with_data)

        c = digest["comparison"]
        # Previous week: 40 + 60 + 25 = 125.00
        assert c["prev_total_spent"] == 125.00
        # Change: (182.5 - 125) / 125 * 100 = 46%
        assert c["change_pct"] == 46.0
        assert c["trend"] == "up"

    def test_category_breakdown(self, app, user_with_data):
        from app.services.digest import generate_digest

        with app.app_context():
            digest = generate_digest(user_with_data)

        cats = digest["by_category"]
        assert len(cats) == 3
        # Dining (85) is highest
        assert cats[0]["name"] == "Dining Out"
        assert cats[0]["amount"] == 85.00
        # Percentages sum close to 100
        total_pct = sum(c["pct_of_total"] for c in cats)
        assert 99.0 <= total_pct <= 101.0

    def test_daily_breakdown_seven_days(self, app, user_with_data):
        from app.services.digest import generate_digest

        with app.app_context():
            digest = generate_digest(user_with_data)

        daily = digest["daily_breakdown"]
        assert len(daily) == 7
        # Verify day names present
        day_names = [d["day_name"] for d in daily]
        assert "Monday" in day_names

    def test_anomaly_detection(self, app, user_with_data):
        from app.services.digest import generate_digest

        with app.app_context():
            digest = generate_digest(user_with_data)

        anomalies = digest["anomalies"]
        # Dining went from 25 to 85 = +240%
        dining_anomaly = next(
            (a for a in anomalies if a["category"] == "Dining Out"), None
        )
        assert dining_anomaly is not None
        assert dining_anomaly["direction"] == "up"
        assert dining_anomaly["change_pct"] == 240.0

        # Transport went from 60 to 30 = -50%
        transport_anomaly = next(
            (a for a in anomalies if a["category"] == "Transport"), None
        )
        assert transport_anomaly is not None
        assert transport_anomaly["direction"] == "down"

    def test_upcoming_bills(self, app, user_with_data):
        from app.services.digest import generate_digest

        with app.app_context():
            digest = generate_digest(user_with_data)

        bills = digest["upcoming_bills"]
        assert len(bills) == 1
        assert bills[0]["name"] == "Netflix"
        assert bills[0]["amount"] == 15.99

    def test_top_expense(self, app, user_with_data):
        from app.services.digest import generate_digest

        with app.app_context():
            digest = generate_digest(user_with_data)

        top = digest["top_expense"]
        assert top["amount"] == 85.00
        assert top["category"] == "Dining Out"
        assert top["notes"] == "Birthday dinner"

    def test_narrative_generated(self, app, user_with_data):
        from app.services.digest import generate_digest

        with app.app_context():
            digest = generate_digest(user_with_data)

        # Should have heuristic narrative (no Gemini key in tests)
        assert len(digest["narrative"]) > 50
        assert "182.50" in digest["narrative"]

    def test_empty_week(self, app, auth_header):
        """Digest with no expenses returns zero totals gracefully."""
        from app.services.digest import generate_digest

        with app.app_context():
            user = db.session.query(User).filter_by(email="test@x.com").first()
            digest = generate_digest(user.id)

        assert digest["summary"]["total_spent"] == 0.0
        assert digest["summary"]["transaction_count"] == 0
        assert digest["comparison"]["trend"] == "stable"
        assert digest["by_category"] == []
        assert digest["top_expense"] is None

    def test_custom_reference_date(self, app, user_with_data):
        from app.services.digest import generate_digest

        with app.app_context():
            # Use a date far in the past — should return empty
            digest = generate_digest(user_with_data, reference_date=date(2020, 1, 15))

        assert digest["summary"]["total_spent"] == 0.0


# ─── API Endpoint Tests ──────────────────────────────────────────


class TestDigestEndpoints:
    def test_weekly_endpoint_200(self, client, auth_header, user_with_data):
        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "period" in data
        assert "narrative" in data
        assert data["summary"]["total_spent"] == 182.50

    def test_weekly_with_date_param(self, client, auth_header, user_with_data):
        r = client.get("/digest/weekly?date=2020-03-15", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["summary"]["total_spent"] == 0.0

    def test_weekly_invalid_date(self, client, auth_header):
        r = client.get("/digest/weekly?date=not-a-date", headers=auth_header)
        assert r.status_code == 400

    def test_highlights_endpoint(self, client, auth_header, user_with_data):
        r = client.get("/digest/highlights", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "total_spent" in data
        assert "narrative" in data
        assert "trend" in data
        assert data["total_spent"] == 182.50

    def test_requires_auth(self, client):
        r = client.get("/digest/weekly")
        assert r.status_code == 401


# ─── Edge Cases ──────────────────────────────────────────────────


class TestDigestEdgeCases:
    def test_single_expense(self, app, auth_header):
        """Digest with exactly one expense."""
        from app.services.digest import generate_digest

        with app.app_context():
            user = db.session.query(User).filter_by(email="test@x.com").first()
            today = date.today()
            last_monday = today - timedelta(days=today.weekday() + 7)
            exp = Expense(
                user_id=user.id,
                amount=Decimal("99.99"),
                spent_at=last_monday + timedelta(days=2),
                expense_type="EXPENSE",
                notes="Solo purchase",
            )
            db.session.add(exp)
            db.session.commit()

            digest = generate_digest(user.id)

        assert digest["summary"]["total_spent"] == 99.99
        assert digest["summary"]["transaction_count"] == 1
        assert digest["top_expense"]["amount"] == 99.99

    def test_all_income_no_expenses(self, app, auth_header):
        """Week with only income entries."""
        from app.services.digest import generate_digest

        with app.app_context():
            user = db.session.query(User).filter_by(email="test@x.com").first()
            today = date.today()
            last_monday = today - timedelta(days=today.weekday() + 7)
            inc = Expense(
                user_id=user.id,
                amount=Decimal("1000.00"),
                spent_at=last_monday,
                expense_type="INCOME",
                notes="Paycheck",
            )
            db.session.add(inc)
            db.session.commit()

            digest = generate_digest(user.id)

        assert digest["summary"]["total_spent"] == 0.0
        assert digest["summary"]["total_income"] == 1000.00
        assert digest["summary"]["net_flow"] == 1000.00
