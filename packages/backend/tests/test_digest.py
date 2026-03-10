import pytest
from app.extensions import db
from app.models import (
    User,
    Category,
    Expense,
    Bill,
    BillCadence,
    AuditLog,
)
from datetime import date, timedelta


@pytest.fixture()
def seeded_digest(client, auth_header):
    """Create sample data for weekly digest testing."""
    with client.application.app_context():
        user = db.session.query(User).filter_by(
            email="test@example.com"
        ).first()
        uid = user.id

        # Categories
        groceries = Category(user_id=uid, name="Groceries")
        transport = Category(user_id=uid, name="Transport")
        dining = Category(user_id=uid, name="Dining")
        db.session.add_all([groceries, transport, dining])
        db.session.flush()

        today = date(2026, 3, 10)

        # Current week expenses (March 4–10)
        expenses = [
            Expense(user_id=uid, category_id=groceries.id, amount=50.00,
                    notes="weekly groceries", spent_at=date(2026, 3, 4)),
            Expense(user_id=uid, category_id=transport.id, amount=15.00,
                    notes="bus pass", spent_at=date(2026, 3, 5)),
            Expense(user_id=uid, category_id=dining.id, amount=30.00,
                    notes="dinner out", spent_at=date(2026, 3, 7)),
            Expense(user_id=uid, category_id=groceries.id, amount=25.00,
                    notes="snacks", spent_at=date(2026, 3, 9)),
            # Income this week
            Expense(user_id=uid, amount=500.00, expense_type="INCOME",
                    notes="freelance payment", spent_at=date(2026, 3, 6)),
        ]
        db.session.add_all(expenses)

        # Previous week expenses (Feb 25 – Mar 3)
        prev_expenses = [
            Expense(user_id=uid, category_id=groceries.id, amount=40.00,
                    notes="prev groceries", spent_at=date(2026, 2, 25)),
            Expense(user_id=uid, category_id=transport.id, amount=10.00,
                    notes="prev bus", spent_at=date(2026, 2, 27)),
            # Income previous week
            Expense(user_id=uid, amount=300.00, expense_type="INCOME",
                    notes="prev freelance", spent_at=date(2026, 2, 26)),
        ]
        db.session.add_all(prev_expenses)

        # Upcoming bill
        bill = Bill(
            user_id=uid,
            name="Internet",
            amount=49.99,
            next_due_date=date(2026, 3, 15),
            cadence=BillCadence.MONTHLY,
            active=True,
        )
        db.session.add(bill)
        db.session.commit()

    return auth_header


# ─── Authentication ───────────────────────────────────────────────


class TestDigestAuth:
    def test_weekly_requires_auth(self, client):
        r = client.get("/digest/weekly")
        assert r.status_code == 401

    def test_history_requires_auth(self, client):
        r = client.get("/digest/weekly/history")
        assert r.status_code == 401


# ─── Weekly Digest ────────────────────────────────────────────────


class TestWeeklyDigest:
    def test_returns_200(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        assert r.status_code == 200

    def test_has_period(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        assert data["period"]["week_start"] == "2026-03-04"
        assert data["period"]["week_end"] == "2026-03-10"

    def test_summary_totals(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        summary = data["summary"]
        # Expenses: 50 + 15 + 30 + 25 = 120
        assert summary["total_expenses"] == 120.0
        # Income: 500
        assert summary["total_income"] == 500.0
        # Net: 500 - 120 = 380
        assert summary["net_flow"] == 380.0

    def test_previous_period_data(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        prev = data["previous_period"]
        # Previous expenses: 40 + 10 = 50
        assert prev["total_expenses"] == 50.0
        # Previous income: 300
        assert prev["total_income"] == 300.0

    def test_expense_change_pct(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        # Change: (120 - 50) / 50 * 100 = 140%
        assert data["summary"]["expense_change_pct"] == 140.0

    def test_income_change_pct(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        # Change: (500 - 300) / 300 * 100 ≈ 66.67%
        assert abs(data["summary"]["income_change_pct"] - 66.67) < 0.01

    def test_top_categories(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        cats = data["top_categories"]
        assert len(cats) == 3
        # Groceries should be first (75 > 30 > 15)
        assert cats[0]["category_name"] == "Groceries"
        assert cats[0]["amount"] == 75.0

    def test_top_categories_share_pct(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        cats = data["top_categories"]
        total_pct = sum(c["share_pct"] for c in cats)
        assert abs(total_pct - 100.0) < 0.1

    def test_daily_breakdown_has_7_days(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        daily = data["daily_breakdown"]
        assert len(daily) == 7
        assert daily[0]["date"] == "2026-03-04"
        assert daily[6]["date"] == "2026-03-10"

    def test_daily_breakdown_amounts(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        daily = data["daily_breakdown"]
        # Mar 4 = 50, Mar 5 = 15, Mar 6 = 0, Mar 7 = 30,
        # Mar 8 = 0, Mar 9 = 25, Mar 10 = 0
        assert daily[0]["amount"] == 50.0
        assert daily[1]["amount"] == 15.0
        assert daily[2]["amount"] == 0.0
        assert daily[3]["amount"] == 30.0
        assert daily[5]["amount"] == 25.0

    def test_upcoming_bills(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        bills = data["upcoming_bills"]
        assert len(bills) == 1
        assert bills[0]["name"] == "Internet"
        assert bills[0]["amount"] == 49.99

    def test_insights_present(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        insights = data["insights"]
        assert isinstance(insights, list)
        assert len(insights) > 0

    def test_insights_spending_increase_warning(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        warnings = [i for i in data["insights"] if i["type"] == "warning"]
        # 140% increase should trigger a warning
        assert any("increased" in w["message"].lower() for w in warnings)

    def test_insights_positive_savings(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        positives = [i for i in data["insights"] if i["type"] == "positive"]
        assert any("saved" in p["message"].lower() for p in positives)

    def test_insights_bill_reminder(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        data = r.get_json()
        infos = [i for i in data["insights"] if i["type"] == "info"]
        assert any("bill" in i["message"].lower() for i in infos)


# ─── Date Validation ──────────────────────────────────────────────


class TestDigestDateValidation:
    def test_invalid_date_format(self, client, auth_header):
        r = client.get("/digest/weekly?date=not-a-date",
                       headers=auth_header)
        assert r.status_code == 400

    def test_defaults_to_today(self, client, auth_header):
        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "period" in data


# ─── Empty Data ───────────────────────────────────────────────────


class TestDigestEmptyData:
    def test_empty_user_gets_zeros(self, client, auth_header):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["summary"]["total_expenses"] == 0.0
        assert data["summary"]["total_income"] == 0.0
        assert data["summary"]["net_flow"] == 0.0

    def test_empty_user_gets_no_data_insight(self, client, auth_header):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=auth_header)
        data = r.get_json()
        messages = [i["message"] for i in data["insights"]]
        assert any("no transactions" in m.lower() for m in messages)


# ─── History Endpoint ─────────────────────────────────────────────


class TestDigestHistory:
    def test_returns_200(self, client, seeded_digest):
        r = client.get("/digest/weekly/history",
                       headers=seeded_digest)
        assert r.status_code == 200

    def test_default_4_weeks(self, client, seeded_digest):
        r = client.get("/digest/weekly/history",
                       headers=seeded_digest)
        data = r.get_json()
        assert data["weeks"] == 4
        assert len(data["history"]) == 4

    def test_custom_weeks(self, client, seeded_digest):
        r = client.get("/digest/weekly/history?weeks=2",
                       headers=seeded_digest)
        data = r.get_json()
        assert data["weeks"] == 2
        assert len(data["history"]) == 2

    def test_max_12_weeks(self, client, seeded_digest):
        r = client.get("/digest/weekly/history?weeks=99",
                       headers=seeded_digest)
        data = r.get_json()
        assert data["weeks"] == 12


# ─── Audit Logging ────────────────────────────────────────────────


class TestDigestAudit:
    def test_creates_audit_log(self, client, seeded_digest):
        r = client.get("/digest/weekly?date=2026-03-10",
                       headers=seeded_digest)
        assert r.status_code == 200
        with client.application.app_context():
            logs = db.session.query(AuditLog).filter_by(
                action="WEEKLY_DIGEST_VIEWED"
            ).all()
            assert len(logs) >= 1
