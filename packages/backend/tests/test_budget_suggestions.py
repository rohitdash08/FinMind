"""
Tests for Dynamic Budget Suggestions (Issue #73).

Covers:
- GET /budget/suggestions returns correct structure
- Suggestions based on spending data (avg × reduction factor)
- confidence: high / medium / low based on data richness + variance
- saving_opportunity = avg - suggested
- months param (3-6), default 3
- months < 3 or > 6 → 400
- reduction_pct param (0-50), default 10
- reduction_pct out of range → 400
- invalid anchor → 400
- Auth required
- User isolation
- Empty history: no suggestions, safe defaults
- 50/30/20 income targets present when income available
- Suggestions sorted by saving_opportunity descending
- Unit tests: get_budget_suggestions
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Category, Expense
from app.services.budget_suggestions import get_budget_suggestions


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="bs@test.com", password="pass1234"):
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

class TestGetBudgetSuggestions:
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
        uid = self._make_user(app_fixture, "bsu_struct@test.com")
        with app_fixture.app_context():
            result = get_budget_suggestions(uid, months=3)
        for k in ("suggestions", "total_suggested", "income_summary",
                  "overall_confidence", "data_months_used", "generated_at"):
            assert k in result

    def test_empty_history_no_crash(self, app_fixture):
        uid = self._make_user(app_fixture, "bsu_empty@test.com")
        with app_fixture.app_context():
            result = get_budget_suggestions(uid, months=3)
        assert result["suggestions"] == []
        assert result["total_suggested"] == 0.0

    def test_suggestion_below_average(self, app_fixture):
        uid = self._make_user(app_fixture, "bsu_below@test.com")
        with app_fixture.app_context():
            for d in [5, 35, 65]:
                db.session.add(Expense(
                    user_id=uid, amount=Decimal("1000"), currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=d), notes="x",
                ))
            db.session.commit()
            result = get_budget_suggestions(uid, months=3, reduction_pct=10)

        s = result["suggestions"][0]
        assert s["suggested_limit"] < s["current_avg_spend"]
        assert s["saving_opportunity"] > 0

    def test_zero_reduction_suggests_current_avg(self, app_fixture):
        uid = self._make_user(app_fixture, "bsu_zero@test.com")
        with app_fixture.app_context():
            for d in [5, 35, 65]:
                db.session.add(Expense(
                    user_id=uid, amount=Decimal("500"), currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=d), notes="x",
                ))
            db.session.commit()
            result = get_budget_suggestions(uid, months=3, reduction_pct=0)

        s = result["suggestions"][0]
        assert s["saving_opportunity"] == pytest.approx(0.0, abs=0.1)

    def test_income_targets_present_when_income_available(self, app_fixture):
        uid = self._make_user(app_fixture, "bsu_income@test.com")
        with app_fixture.app_context():
            db.session.add(Expense(
                user_id=uid, amount=Decimal("5000"), currency="INR",
                expense_type="INCOME",
                spent_at=date.today() - timedelta(days=5), notes="salary",
            ))
            db.session.commit()
            result = get_budget_suggestions(uid, months=3)

        assert "needs_target" in result["income_summary"]
        assert "wants_target" in result["income_summary"]
        assert "savings_target" in result["income_summary"]

    def test_user_isolation(self, app_fixture):
        uid1 = self._make_user(app_fixture, "bsu_iso1@test.com")
        uid2 = self._make_user(app_fixture, "bsu_iso2@test.com")
        with app_fixture.app_context():
            db.session.add(Expense(
                user_id=uid1, amount=Decimal("9000"), currency="INR",
                expense_type="EXPENSE",
                spent_at=date.today() - timedelta(days=5), notes="big",
            ))
            db.session.commit()
            result = get_budget_suggestions(uid2, months=3)

        assert result["suggestions"] == []

    def test_confidence_field_in_suggestions(self, app_fixture):
        uid = self._make_user(app_fixture, "bsu_conf@test.com")
        with app_fixture.app_context():
            for d in [5, 35, 65]:
                db.session.add(Expense(
                    user_id=uid, amount=Decimal("800"), currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=d), notes="x",
                ))
            db.session.commit()
            result = get_budget_suggestions(uid, months=3)

        assert all(s["confidence"] in ("high", "medium", "low")
                   for s in result["suggestions"])


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestBudgetSuggestionsEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/budget/suggestions").status_code == 401

    def test_returns_200(self, client, app_fixture):
        h = _auth(client, "bse1@test.com")
        r = client.get("/budget/suggestions", headers=h)
        assert r.status_code == 200

    def test_response_structure(self, client, app_fixture):
        h = _auth(client, "bse2@test.com")
        d = client.get("/budget/suggestions", headers=h).get_json()
        for k in ("suggestions", "total_suggested", "income_summary",
                  "overall_confidence", "data_months_used", "generated_at"):
            assert k in d

    def test_months_too_small_returns_400(self, client, app_fixture):
        h = _auth(client, "bse3@test.com")
        assert client.get("/budget/suggestions?months=2", headers=h).status_code == 400

    def test_months_too_large_returns_400(self, client, app_fixture):
        h = _auth(client, "bse4@test.com")
        assert client.get("/budget/suggestions?months=7", headers=h).status_code == 400

    def test_months_valid_range(self, client, app_fixture):
        h = _auth(client, "bse5@test.com")
        for m in [3, 4, 5, 6]:
            r = client.get(f"/budget/suggestions?months={m}", headers=h)
            assert r.status_code == 200

    def test_reduction_pct_invalid_returns_400(self, client, app_fixture):
        h = _auth(client, "bse6@test.com")
        assert client.get("/budget/suggestions?reduction_pct=-1", headers=h).status_code == 400
        assert client.get("/budget/suggestions?reduction_pct=51", headers=h).status_code == 400
        assert client.get("/budget/suggestions?reduction_pct=abc", headers=h).status_code == 400

    def test_reduction_pct_zero_allowed(self, client, app_fixture):
        h = _auth(client, "bse7@test.com")
        assert client.get("/budget/suggestions?reduction_pct=0", headers=h).status_code == 200

    def test_invalid_anchor_returns_400(self, client, app_fixture):
        h = _auth(client, "bse8@test.com")
        assert client.get("/budget/suggestions?anchor=bad", headers=h).status_code == 400

    def test_suggestion_below_avg_with_data(self, client, app_fixture):
        h = _auth(client, "bse9@test.com")
        uid = _get_uid(app_fixture, "bse9@test.com")
        for d in [5, 35, 65]:
            _seed(app_fixture, uid, 1000, days_ago=d)

        d = client.get("/budget/suggestions?reduction_pct=10", headers=h).get_json()
        if d["suggestions"]:
            s = d["suggestions"][0]
            assert s["suggested_limit"] < s["current_avg_spend"]

    def test_suggestions_sorted_by_saving_opportunity(self, client, app_fixture):
        h = _auth(client, "bse10@test.com")
        uid = _get_uid(app_fixture, "bse10@test.com")
        cat_a = _seed_category(app_fixture, uid, "BigCat")
        cat_b = _seed_category(app_fixture, uid, "SmallCat")

        for d in [5, 35, 65]:
            _seed(app_fixture, uid, 3000, days_ago=d, category_id=cat_a)
            _seed(app_fixture, uid, 100, days_ago=d, category_id=cat_b)

        data = client.get("/budget/suggestions", headers=h).get_json()
        suggestions = data["suggestions"]
        if len(suggestions) >= 2:
            # Should be sorted descending by saving_opportunity
            for i in range(len(suggestions) - 1):
                assert suggestions[i]["saving_opportunity"] >= suggestions[i+1]["saving_opportunity"]

    def test_user_isolation(self, client, app_fixture):
        h1 = _auth(client, "bsiso1@test.com")
        h2 = _auth(client, "bsiso2@test.com")
        uid1 = _get_uid(app_fixture, "bsiso1@test.com")
        for d in [5, 35, 65]:
            _seed(app_fixture, uid1, 5000, days_ago=d)

        d2 = client.get("/budget/suggestions", headers=h2).get_json()
        assert d2["suggestions"] == []
        assert d2["total_suggested"] == 0.0

    def test_income_summary_present(self, client, app_fixture):
        h = _auth(client, "bse11@test.com")
        d = client.get("/budget/suggestions", headers=h).get_json()
        assert "avg_monthly_income" in d["income_summary"]

    def test_rationale_field_in_suggestion(self, client, app_fixture):
        h = _auth(client, "bse12@test.com")
        uid = _get_uid(app_fixture, "bse12@test.com")
        for d in [5, 35, 65]:
            _seed(app_fixture, uid, 500, days_ago=d)
        data = client.get("/budget/suggestions", headers=h).get_json()
        if data["suggestions"]:
            assert "rationale" in data["suggestions"][0]
