"""
Tests for Autonomous Budget Optimization (Issue #92).

Covers:
- GET /budget/optimize returns correct structure
- Overspending detection flags high-share categories
- Trend detection: increasing / decreasing / stable / insufficient_data
- Reallocation recommendations are generated for overspent categories
- 50/30/20 target budget recommendation included when income is present
- Summary endpoint returns subset of full response
- Input validation: months out of range, bad anchor date
- Auth required on all endpoints
- Empty spending history returns safe defaults
- Isolation between users (each sees only their own data)
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Category, Expense
from app.services.budget_optimizer import (
    _compute_trend,
    _detect_overspending,
    _iter_months,
    get_budget_optimization,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="budget@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _get_uid(app_fixture, email):
    from app.models import User
    with app_fixture.app_context():
        u = db.session.query(User).filter_by(email=email).first()
        return u.id if u else None


def _seed_expense(app_fixture, user_id, amount, expense_type="EXPENSE",
                  days_ago=5, category_id=None, notes="test"):
    with app_fixture.app_context():
        spent = date.today() - timedelta(days=days_ago)
        db.session.add(Expense(
            user_id=user_id,
            amount=Decimal(str(amount)),
            currency="INR",
            expense_type=expense_type,
            spent_at=spent,
            notes=notes,
            category_id=category_id,
        ))
        db.session.commit()


def _seed_category(app_fixture, user_id, name="Food"):
    with app_fixture.app_context():
        cat = Category(user_id=user_id, name=name)
        db.session.add(cat)
        db.session.commit()
        return cat.id


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — service functions
# ─────────────────────────────────────────────────────────────────────────────

class TestIterMonths:
    def test_yields_n_months(self):
        result = list(_iter_months(date(2026, 3, 15), 3))
        assert len(result) == 3

    def test_wraps_year_boundary(self):
        result = list(_iter_months(date(2026, 1, 1), 3))
        assert (2025, 12) in result
        assert (2025, 11) in result

    def test_single_month(self):
        result = list(_iter_months(date(2026, 6, 1), 1))
        assert result == [(2026, 6)]


class TestDetectOverspending:
    def test_flags_disproportionate_category(self):
        # Category A gets 80% of spend — way above the 1.5× threshold
        totals = {"1": 800.0, "2": 100.0, "3": 100.0}
        flagged = _detect_overspending(totals, 1000.0)
        ids = [f["category_id"] for f in flagged]
        assert "1" in ids

    def test_no_flags_when_balanced(self):
        totals = {"1": 100.0, "2": 100.0, "3": 100.0}
        flagged = _detect_overspending(totals, 300.0)
        assert flagged == []

    def test_empty_totals(self):
        assert _detect_overspending({}, 0.0) == []

    def test_returns_share_pct(self):
        totals = {"1": 900.0, "2": 100.0}
        flagged = _detect_overspending(totals, 1000.0)
        assert any(f["share_pct"] == 90.0 for f in flagged)


class TestComputeTrend:
    def test_increasing(self):
        result = _compute_trend([100.0, 120.0, 150.0])
        assert result["direction"] == "increasing"
        assert result["avg_mom_change_pct"] > 0

    def test_decreasing(self):
        result = _compute_trend([150.0, 120.0, 100.0])
        assert result["direction"] == "decreasing"

    def test_stable(self):
        result = _compute_trend([100.0, 101.0, 100.5])
        assert result["direction"] == "stable"

    def test_insufficient_data(self):
        result = _compute_trend([100.0])
        assert result["direction"] == "insufficient_data"
        assert result["avg_mom_change_pct"] is None

    def test_empty_list(self):
        result = _compute_trend([])
        assert result["direction"] == "insufficient_data"


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — service
# ─────────────────────────────────────────────────────────────────────────────

class TestGetBudgetOptimization:
    def test_empty_history_returns_safe_defaults(self, app_fixture):
        h = _auth(None.__class__.__new__(None.__class__), "empty@budget.test")  # unused
        _auth_email = "empty_svc@budget.test"
        # Register via service directly won't work; use app context only
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email=_auth_email, password_hash=generate_password_hash("x"), preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            uid = u.id
            result = get_budget_optimization(uid, months=3)

        assert result["avg_monthly_expenses"] == 0.0
        assert result["avg_monthly_income"] == 0.0
        assert result["net_flow"] == 0.0
        assert result["overspending_alerts"] == []
        assert isinstance(result["monthly_breakdown"], list)
        assert len(result["monthly_breakdown"]) == 3

    def test_correct_structure(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email="struct@budget.test", password_hash=generate_password_hash("x"), preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            uid = u.id
            result = get_budget_optimization(uid, months=1)

        required_keys = {
            "analysis_period_months", "monthly_breakdown", "avg_monthly_expenses",
            "avg_monthly_income", "net_flow", "trend", "overspending_alerts",
            "category_totals", "recommendations", "generated_at",
        }
        assert required_keys.issubset(result.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestBudgetOptimizeEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/budget/optimize").status_code == 401
        assert client.get("/budget/optimize/summary").status_code == 401

    def test_returns_200_with_valid_auth(self, client, app_fixture):
        h = _auth(client, "opt1@budget.test")
        r = client.get("/budget/optimize", headers=h)
        assert r.status_code == 200

    def test_default_months_is_3(self, client, app_fixture):
        h = _auth(client, "opt2@budget.test")
        r = client.get("/budget/optimize", headers=h)
        assert r.get_json()["analysis_period_months"] == 3

    def test_custom_months_param(self, client, app_fixture):
        h = _auth(client, "opt3@budget.test")
        r = client.get("/budget/optimize?months=6", headers=h)
        assert r.status_code == 200
        assert r.get_json()["analysis_period_months"] == 6

    def test_months_out_of_range_returns_400(self, client, app_fixture):
        h = _auth(client, "opt4@budget.test")
        assert client.get("/budget/optimize?months=0", headers=h).status_code == 400
        assert client.get("/budget/optimize?months=13", headers=h).status_code == 400

    def test_invalid_months_returns_400(self, client, app_fixture):
        h = _auth(client, "opt5@budget.test")
        r = client.get("/budget/optimize?months=abc", headers=h)
        assert r.status_code == 400

    def test_invalid_anchor_returns_400(self, client, app_fixture):
        h = _auth(client, "opt6@budget.test")
        r = client.get("/budget/optimize?anchor=not-a-date", headers=h)
        assert r.status_code == 400

    def test_valid_anchor_param(self, client, app_fixture):
        h = _auth(client, "opt7@budget.test")
        r = client.get("/budget/optimize?anchor=2026-03-01", headers=h)
        assert r.status_code == 200

    def test_response_structure(self, client, app_fixture):
        h = _auth(client, "opt8@budget.test")
        d = client.get("/budget/optimize", headers=h).get_json()
        assert "trend" in d
        assert "direction" in d["trend"]
        assert "recommendations" in d
        assert "monthly_breakdown" in d
        assert isinstance(d["monthly_breakdown"], list)

    def test_overspending_detected_and_flagged(self, client, app_fixture):
        h = _auth(client, "opt9@budget.test")
        uid = _get_uid(app_fixture, "opt9@budget.test")
        cat_id = _seed_category(app_fixture, uid, "Entertainment")

        # Seed a dominant expense in one category this month
        _seed_expense(app_fixture, uid, 900, category_id=cat_id, days_ago=3)
        _seed_expense(app_fixture, uid, 50, days_ago=3)   # small uncategorised

        r = client.get("/budget/optimize?months=1", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert len(d["overspending_alerts"]) >= 1
        alert = d["overspending_alerts"][0]
        assert "category_name" in alert
        assert "reason" in alert
        assert "savings_opportunity" in alert or "excess" in alert

    def test_income_triggers_50_30_20_recommendation(self, client, app_fixture):
        h = _auth(client, "opt10@budget.test")
        uid = _get_uid(app_fixture, "opt10@budget.test")
        _seed_expense(app_fixture, uid, 5000, expense_type="INCOME", days_ago=5)
        _seed_expense(app_fixture, uid, 1000, days_ago=5)

        r = client.get("/budget/optimize?months=1", headers=h)
        d = r.get_json()
        types = [rec["type"] for rec in d["recommendations"]]
        assert "target_budget" in types

    def test_net_flow_calculation(self, client, app_fixture):
        h = _auth(client, "opt11@budget.test")
        uid = _get_uid(app_fixture, "opt11@budget.test")
        _seed_expense(app_fixture, uid, 3000, expense_type="INCOME", days_ago=3)
        _seed_expense(app_fixture, uid, 2000, expense_type="EXPENSE", days_ago=3)

        r = client.get("/budget/optimize?months=1", headers=h)
        d = r.get_json()
        assert d["net_flow"] == pytest.approx(1000.0, abs=1.0)

    def test_user_isolation(self, client, app_fixture):
        h1 = _auth(client, "iso1@budget.test")
        h2 = _auth(client, "iso2@budget.test")
        uid1 = _get_uid(app_fixture, "iso1@budget.test")
        _seed_expense(app_fixture, uid1, 5000, days_ago=5)

        # User2 should see 0 expenses even though User1 has 5000
        r = client.get("/budget/optimize?months=1", headers=h2)
        assert r.get_json()["avg_monthly_expenses"] == 0.0


class TestBudgetSummaryEndpoint:
    def test_returns_200(self, client, app_fixture):
        h = _auth(client, "sum1@budget.test")
        r = client.get("/budget/optimize/summary", headers=h)
        assert r.status_code == 200

    def test_summary_keys(self, client, app_fixture):
        h = _auth(client, "sum2@budget.test")
        d = client.get("/budget/optimize/summary", headers=h).get_json()
        assert "trend" in d
        assert "net_flow" in d
        assert "overspending_alert_count" in d
        assert "top_recommendations" in d
        assert isinstance(d["top_recommendations"], list)
        assert len(d["top_recommendations"]) <= 3

    def test_summary_has_no_monthly_breakdown(self, client, app_fixture):
        h = _auth(client, "sum3@budget.test")
        d = client.get("/budget/optimize/summary", headers=h).get_json()
        # Summary is lightweight — no verbose breakdown
        assert "monthly_breakdown" not in d
        assert "category_totals" not in d
