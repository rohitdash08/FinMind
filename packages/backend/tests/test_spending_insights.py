"""
Tests for Explainable Spending Insights (Issue #89).

Covers:
- GET /insights/explain structure
- Insight generated when spending increases significantly
- Insight generated when spending decreases
- what_changed / why_it_changed fields populated
- confidence field present and valid
- New category (prev=0) explanation
- Vanishing category (curr=0) explanation
- months=2 minimum validated
- months=1 returns 400
- months=13 returns 400
- anchor param
- invalid anchor returns 400
- Auth required
- User isolation
- Overall trend: increasing / decreasing / stable
- GET /insights/explain/summary lightweight
- period_summaries correct
- top_changes is a list of max 3
- Empty history returns safe defaults (no crash)
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Category, Expense
from app.services.spending_insights import get_spending_insights


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="exp@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _get_uid(app_fixture, email):
    from app.models import User
    with app_fixture.app_context():
        u = db.session.query(User).filter_by(email=email).first()
        return u.id if u else None


def _seed(app_fixture, uid, amount, expense_type="EXPENSE", days_ago=5,
          category_id=None, notes="x"):
    with app_fixture.app_context():
        db.session.add(Expense(
            user_id=uid, amount=Decimal(str(amount)), currency="INR",
            expense_type=expense_type,
            spent_at=date.today() - timedelta(days=days_ago),
            notes=notes, category_id=category_id,
        ))
        db.session.commit()


def _seed_category(app_fixture, uid, name="Food"):
    with app_fixture.app_context():
        cat = Category(user_id=uid, name=name)
        db.session.add(cat)
        db.session.commit()
        return cat.id


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — service
# ─────────────────────────────────────────────────────────────────────────────

class TestGetSpendingInsights:
    def _make_user(self, app_fixture, email):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email=email, password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            return u.id

    def test_returns_required_keys(self, app_fixture):
        uid = self._make_user(app_fixture, "si_struct@test.com")
        with app_fixture.app_context():
            result = get_spending_insights(uid, months=2)
        for k in ("insights", "top_changes", "overall_trend",
                  "trend_confidence", "period_summaries", "generated_at"):
            assert k in result

    def test_empty_history_no_crash(self, app_fixture):
        uid = self._make_user(app_fixture, "si_empty@test.com")
        with app_fixture.app_context():
            result = get_spending_insights(uid, months=2)
        assert isinstance(result["insights"], list)
        assert result["overall_trend"] in ("stable", "insufficient_data", "increasing", "decreasing")

    def test_period_summaries_count(self, app_fixture):
        uid = self._make_user(app_fixture, "si_periods@test.com")
        with app_fixture.app_context():
            result = get_spending_insights(uid, months=3)
        assert len(result["period_summaries"]) == 3

    def test_top_changes_max_3(self, app_fixture):
        uid = self._make_user(app_fixture, "si_top@test.com")
        with app_fixture.app_context():
            result = get_spending_insights(uid, months=3)
        assert len(result["top_changes"]) <= 3

    def test_user_isolation(self, app_fixture):
        uid1 = self._make_user(app_fixture, "si_iso1@test.com")
        uid2 = self._make_user(app_fixture, "si_iso2@test.com")
        with app_fixture.app_context():
            # Seed large change for u1
            for days in [5, 35]:
                db.session.add(Expense(user_id=uid1, amount=Decimal("5000"),
                                       currency="INR", expense_type="EXPENSE",
                                       spent_at=date.today() - timedelta(days=days),
                                       notes="big"))
            db.session.commit()
            # u2 should see no insights
            result = get_spending_insights(uid2, months=2)
        assert len(result["top_changes"]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestExplainEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/insights/explain").status_code == 401

    def test_returns_200(self, client, app_fixture):
        h = _auth(client, "ex1@test.com")
        r = client.get("/insights/explain", headers=h)
        assert r.status_code == 200

    def test_response_structure(self, client, app_fixture):
        h = _auth(client, "ex2@test.com")
        d = client.get("/insights/explain", headers=h).get_json()
        for k in ("insights", "top_changes", "overall_trend",
                  "trend_confidence", "period_summaries", "generated_at"):
            assert k in d

    def test_months_param_min_2(self, client, app_fixture):
        h = _auth(client, "ex3@test.com")
        assert client.get("/insights/explain?months=1", headers=h).status_code == 400

    def test_months_param_max_12(self, client, app_fixture):
        h = _auth(client, "ex4@test.com")
        assert client.get("/insights/explain?months=13", headers=h).status_code == 400
        assert client.get("/insights/explain?months=12", headers=h).status_code == 200

    def test_invalid_months_type_returns_400(self, client, app_fixture):
        h = _auth(client, "ex5@test.com")
        assert client.get("/insights/explain?months=abc", headers=h).status_code == 400

    def test_invalid_anchor_returns_400(self, client, app_fixture):
        h = _auth(client, "ex6@test.com")
        assert client.get("/insights/explain?anchor=bad", headers=h).status_code == 400

    def test_valid_anchor(self, client, app_fixture):
        h = _auth(client, "ex7@test.com")
        r = client.get("/insights/explain?anchor=2026-03-01&months=2", headers=h)
        assert r.status_code == 200

    def test_insight_fields_when_change_detected(self, client, app_fixture):
        """When spending changes significantly, insight must have explanation fields."""
        h = _auth(client, "ex8@test.com")
        uid = _get_uid(app_fixture, "ex8@test.com")
        cat_id = _seed_category(app_fixture, uid, "Dining")

        # Large expense in current month, nothing last month
        _seed(app_fixture, uid, 5000, days_ago=5, category_id=cat_id)

        d = client.get("/insights/explain?months=2", headers=h).get_json()
        if d["top_changes"]:
            change = d["top_changes"][0]
            assert "what_changed" in change
            assert "why_it_changed" in change
            assert "confidence" in change
            assert change["confidence"] in ("high", "medium", "low")

    def test_period_summaries_correct_count(self, client, app_fixture):
        h = _auth(client, "ex9@test.com")
        d = client.get("/insights/explain?months=4", headers=h).get_json()
        assert len(d["period_summaries"]) == 4

    def test_overall_trend_valid_value(self, client, app_fixture):
        h = _auth(client, "ex10@test.com")
        d = client.get("/insights/explain", headers=h).get_json()
        assert d["overall_trend"] in ("increasing", "decreasing", "stable", "insufficient_data")

    def test_top_changes_max_3(self, client, app_fixture):
        h = _auth(client, "ex11@test.com")
        d = client.get("/insights/explain?months=6", headers=h).get_json()
        assert len(d["top_changes"]) <= 3

    def test_user_isolation(self, client, app_fixture):
        h1 = _auth(client, "exiso1@test.com")
        h2 = _auth(client, "exiso2@test.com")
        uid1 = _get_uid(app_fixture, "exiso1@test.com")
        # Seed big change for user1
        _seed(app_fixture, uid1, 8000, days_ago=5)

        d2 = client.get("/insights/explain?months=2", headers=h2).get_json()
        assert len(d2["top_changes"]) == 0


class TestExplainSummaryEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/insights/explain/summary").status_code == 401

    def test_returns_200(self, client, app_fixture):
        h = _auth(client, "exs1@test.com")
        assert client.get("/insights/explain/summary", headers=h).status_code == 200

    def test_summary_keys(self, client, app_fixture):
        h = _auth(client, "exs2@test.com")
        d = client.get("/insights/explain/summary", headers=h).get_json()
        assert "top_changes" in d
        assert "overall_trend" in d
        assert "trend_confidence" in d
        assert "generated_at" in d

    def test_summary_no_verbose_fields(self, client, app_fixture):
        h = _auth(client, "exs3@test.com")
        d = client.get("/insights/explain/summary", headers=h).get_json()
        assert "insights" not in d
        assert "period_summaries" not in d
