"""Tests for GET /digest/weekly endpoint (Bounty #121)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.extensions import db
from app.models import Category, Expense, User
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_login(client, email="digest@test.com", password="pw123456"):
    """Register + login, return JWT auth header dict."""
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _add_expense(app_fixture, user_id, amount, expense_type="EXPENSE",
                 days_ago=0, notes="", category_id=None):
    """Insert an Expense row directly via the DB session."""
    with app_fixture.app_context():
        e = Expense(
            user_id=user_id,
            amount=Decimal(str(amount)),
            expense_type=expense_type,
            notes=notes,
            spent_at=date.today() - timedelta(days=days_ago),
            category_id=category_id,
            currency="INR",
        )
        db.session.add(e)
        db.session.commit()


def _get_user_id(app_fixture, email):
    with app_fixture.app_context():
        return db.session.query(User).filter_by(email=email).first().id


def _add_category(app_fixture, user_id, name):
    with app_fixture.app_context():
        cat = Category(user_id=user_id, name=name)
        db.session.add(cat)
        db.session.commit()
        return cat.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWeeklyDigest:
    EMAIL = "digest_user@test.com"
    PASSWORD = "hunter2!A"

    @pytest.fixture(autouse=True)
    def setup(self, client, app_fixture):
        self.client = client
        self.app = app_fixture
        self.auth = _register_login(client, self.EMAIL, self.PASSWORD)
        self.user_id = _get_user_id(app_fixture, self.EMAIL)

    # ── Auth guard ──────────────────────────────────────────────────────────

    def test_requires_authentication(self):
        r = self.client.get("/digest/weekly")
        assert r.status_code == 401

    # ── Empty state ─────────────────────────────────────────────────────────

    def test_empty_returns_zeros(self):
        r = self.client.get("/digest/weekly", headers=self.auth)
        assert r.status_code == 200
        data = r.get_json()
        assert data["summary"]["total_expenses"] == 0.0
        assert data["summary"]["total_income"] == 0.0
        assert data["summary"]["net_flow"] == 0.0
        assert data["summary"]["transaction_count"] == 0

    # ── Period dates ─────────────────────────────────────────────────────────

    def test_period_spans_seven_days(self):
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        from datetime import datetime
        start = datetime.strptime(data["period"]["start"], "%Y-%m-%d").date()
        end = datetime.strptime(data["period"]["end"], "%Y-%m-%d").date()
        assert (end - start).days == 7

    # ── Expense counting ─────────────────────────────────────────────────────

    def test_current_week_expenses_counted(self):
        _add_expense(self.app, self.user_id, 100, "EXPENSE", days_ago=1)
        _add_expense(self.app, self.user_id, 200, "EXPENSE", days_ago=3)
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        assert data["summary"]["total_expenses"] == 300.0
        assert data["summary"]["transaction_count"] == 2

    # ── Income tracking ─────────────────────────────────────────────────────

    def test_income_tracked_separately(self):
        _add_expense(self.app, self.user_id, 500, "INCOME", days_ago=2)
        _add_expense(self.app, self.user_id, 150, "EXPENSE", days_ago=2)
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        assert data["summary"]["total_income"] == 500.0
        assert data["summary"]["total_expenses"] == 150.0
        assert data["summary"]["net_flow"] == pytest.approx(350.0)

    # ── Old expenses excluded ────────────────────────────────────────────────

    def test_old_expenses_excluded(self):
        _add_expense(self.app, self.user_id, 999, "EXPENSE", days_ago=8)
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        assert data["summary"]["total_expenses"] == 0.0

    # ── Trend calculation ────────────────────────────────────────────────────

    def test_trend_calculated_vs_prior_week(self):
        # Prior week: 100; current week: 80 => -20%
        _add_expense(self.app, self.user_id, 100, "EXPENSE", days_ago=10)
        _add_expense(self.app, self.user_id, 80, "EXPENSE", days_ago=2)
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        assert data["trends"]["expenses_vs_prior_week_pct"] == pytest.approx(-20.0)

    def test_trend_zero_when_no_prior_data(self):
        _add_expense(self.app, self.user_id, 50, "EXPENSE", days_ago=1)
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        # No prior week data => 0.0
        assert data["trends"]["expenses_vs_prior_week_pct"] == 0.0

    # ── Category breakdown ───────────────────────────────────────────────────

    def test_category_breakdown_present(self):
        cat_id = _add_category(self.app, self.user_id, "Food")
        _add_expense(self.app, self.user_id, 100, "EXPENSE", days_ago=1,
                     category_id=cat_id)
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        cats = {c["category"]: c for c in data["category_breakdown"]}
        assert "Food" in cats
        assert cats["Food"]["total"] == 100.0
        assert cats["Food"]["pct_of_expenses"] == pytest.approx(100.0)

    def test_category_breakdown_pct_sums_to_100(self):
        c1 = _add_category(self.app, self.user_id, "Food")
        c2 = _add_category(self.app, self.user_id, "Transport")
        _add_expense(self.app, self.user_id, 300, "EXPENSE", days_ago=1, category_id=c1)
        _add_expense(self.app, self.user_id, 200, "EXPENSE", days_ago=2, category_id=c2)
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        total_pct = sum(c["pct_of_expenses"] for c in data["category_breakdown"])
        assert total_pct == pytest.approx(100.0, abs=0.2)

    # ── Biggest expense ──────────────────────────────────────────────────────

    def test_biggest_expense_identified(self):
        cat_id = _add_category(self.app, self.user_id, "Housing")
        _add_expense(self.app, self.user_id, 50, "EXPENSE", days_ago=1, notes="Coffee")
        _add_expense(self.app, self.user_id, 450, "EXPENSE", days_ago=2,
                     notes="Rent", category_id=cat_id)
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        biggest = data["trends"]["biggest_expense"]
        assert biggest["amount"] == 450.0
        assert biggest["notes"] == "Rent"

    # ── Insights ─────────────────────────────────────────────────────────────

    def test_insights_always_present(self):
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        assert isinstance(data["insights"], list)
        assert len(data["insights"]) >= 1

    def test_insights_mention_spending_down(self):
        _add_expense(self.app, self.user_id, 200, "EXPENSE", days_ago=10)
        _add_expense(self.app, self.user_id, 100, "EXPENSE", days_ago=2)
        r = self.client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        combined = " ".join(data["insights"]).lower()
        assert "less" in combined or "50.0" in combined

    # ── User isolation ───────────────────────────────────────────────────────

    def test_other_user_data_not_leaked(self, client, app_fixture):
        other_auth = _register_login(client, "other@test.com", "other_pass1")
        other_id = _get_user_id(app_fixture, "other@test.com")
        _add_expense(app_fixture, other_id, 9999, "EXPENSE", days_ago=1)

        r = client.get("/digest/weekly", headers=self.auth)
        data = r.get_json()
        assert data["summary"]["total_expenses"] == 0.0
