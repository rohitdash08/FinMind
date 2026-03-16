"""
Tests for Financial Scenario Simulator — What-If Planning (Issue #94).

Covers:
- POST /scenarios/simulate returns correct structure
- Income change adjustments (pct and fixed)
- Category change adjustments (pct and fixed)
- Fixed cost change adjustments
- Combining multiple adjustments in one request
- delta.net_flow_direction: better / worse / unchanged
- savings_rate_pct computed correctly
- Error handling: unknown type, missing required fields, empty list, >20 items
- 422 returned when all adjustments fail
- GET /scenarios/presets returns list of templates
- Auth required on all endpoints
- User isolation (adjustments are relative to own baseline)
- anchor and months params
- Pure unit tests of _apply_adjustment
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Category, Expense
from app.services.scenario_simulator import (
    ADJUSTMENT_TYPES,
    _apply_adjustment,
    run_scenario,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="sim@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _get_uid(app_fixture, email):
    from app.models import User
    with app_fixture.app_context():
        u = db.session.query(User).filter_by(email=email).first()
        return u.id if u else None


def _seed_expense(app_fixture, user_id, amount, expense_type="EXPENSE",
                  days_ago=5, category_id=None):
    with app_fixture.app_context():
        spent = date.today() - timedelta(days=days_ago)
        db.session.add(Expense(
            user_id=user_id,
            amount=Decimal(str(amount)),
            currency="INR",
            expense_type=expense_type,
            spent_at=spent,
            notes="sim test",
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
# Unit tests — _apply_adjustment
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyAdjustment:
    _base_cats = {"1": 1000.0, "2": 500.0}
    _base_income = 3000.0

    def test_category_pct_decrease(self):
        cats, income, err = _apply_adjustment(
            self._base_cats, self._base_income,
            {"type": "category_change", "category_id": "1", "pct_change": -10},
        )
        assert err is None
        assert cats["1"] == pytest.approx(900.0)
        assert income == self._base_income

    def test_category_pct_increase(self):
        cats, income, err = _apply_adjustment(
            self._base_cats, self._base_income,
            {"type": "category_change", "category_id": "2", "pct_change": 50},
        )
        assert err is None
        assert cats["2"] == pytest.approx(750.0)

    def test_category_fixed_decrease(self):
        cats, income, err = _apply_adjustment(
            self._base_cats, self._base_income,
            {"type": "category_change", "category_id": "1", "amount_change": -200},
        )
        assert err is None
        assert cats["1"] == pytest.approx(800.0)

    def test_category_cannot_go_below_zero(self):
        cats, income, err = _apply_adjustment(
            {"1": 100.0}, self._base_income,
            {"type": "category_change", "category_id": "1", "amount_change": -9999},
        )
        assert err is None
        assert cats["1"] == 0.0

    def test_income_pct_increase(self):
        cats, income, err = _apply_adjustment(
            self._base_cats, 2000.0,
            {"type": "income_change", "pct_change": 15},
        )
        assert err is None
        assert income == pytest.approx(2300.0)

    def test_income_fixed_decrease(self):
        cats, income, err = _apply_adjustment(
            self._base_cats, 2000.0,
            {"type": "income_change", "amount_change": -500},
        )
        assert err is None
        assert income == pytest.approx(1500.0)

    def test_income_loss_100pct(self):
        cats, income, err = _apply_adjustment(
            self._base_cats, 3000.0,
            {"type": "income_change", "pct_change": -100},
        )
        assert err is None
        assert income == 0.0

    def test_fixed_cost_change(self):
        cats, income, err = _apply_adjustment(
            {"fixed:rent": 1000.0}, self._base_income,
            {"type": "fixed_cost_change", "label": "rent", "pct_change": 20},
        )
        assert err is None
        assert cats["fixed:rent"] == pytest.approx(1200.0)

    def test_unknown_type_returns_error(self):
        cats, income, err = _apply_adjustment(
            self._base_cats, self._base_income,
            {"type": "invalid_type"},
        )
        assert err is not None
        assert "unknown adjustment type" in err

    def test_category_change_missing_delta_returns_error(self):
        _, _, err = _apply_adjustment(
            self._base_cats, self._base_income,
            {"type": "category_change", "category_id": "1"},  # no pct or amount
        )
        assert err is not None

    def test_income_change_missing_delta_returns_error(self):
        _, _, err = _apply_adjustment(
            self._base_cats, self._base_income,
            {"type": "income_change"},
        )
        assert err is not None

    def test_new_category_key_created(self):
        cats, _, err = _apply_adjustment(
            {}, self._base_income,
            {"type": "category_change", "category_id": "99", "amount_change": 500},
        )
        assert err is None
        assert cats.get("99") == pytest.approx(500.0)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — run_scenario
# ─────────────────────────────────────────────────────────────────────────────

class TestRunScenario:
    def test_empty_adjustments_baseline_equals_scenario(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email="rs_empty@sim.test", password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            result = run_scenario(u.id, adjustments=[], months=1)

        assert result["baseline"]["expenses"] == result["scenario"]["expenses"]
        assert result["delta"]["net_flow"] == 0.0
        assert result["delta"]["net_flow_direction"] == "unchanged"

    def test_income_increase_improves_net_flow(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email="rs_income@sim.test", password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            spent = date.today() - timedelta(days=5)
            db.session.add(Expense(user_id=u.id, amount=Decimal("5000"),
                                   currency="INR", expense_type="INCOME",
                                   spent_at=spent, notes="salary"))
            db.session.add(Expense(user_id=u.id, amount=Decimal("2000"),
                                   currency="INR", expense_type="EXPENSE",
                                   spent_at=spent, notes="bills"))
            db.session.commit()

            result = run_scenario(u.id, [{"type": "income_change", "pct_change": 10}], months=1)

        assert result["delta"]["net_flow"] > 0
        assert result["delta"]["net_flow_direction"] == "better"

    def test_expense_increase_worsens_net_flow(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email="rs_expense@sim.test", password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            spent = date.today() - timedelta(days=5)
            db.session.add(Expense(user_id=u.id, amount=Decimal("3000"),
                                   currency="INR", expense_type="INCOME",
                                   spent_at=spent, notes="salary"))
            db.session.add(Expense(user_id=u.id, amount=Decimal("1000"),
                                   currency="INR", expense_type="EXPENSE",
                                   spent_at=spent, notes="food", category_id=None))
            db.session.commit()

            result = run_scenario(u.id, [
                {"type": "category_change", "category_id": "uncat", "pct_change": 50}
            ], months=1)

        assert result["delta"]["net_flow"] < 0
        assert result["delta"]["net_flow_direction"] == "worse"

    def test_error_collected_but_valid_adjustments_applied(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email="rs_mixed@sim.test", password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            result = run_scenario(u.id, [
                {"type": "income_change", "pct_change": 10},   # valid
                {"type": "bad_type"},                           # invalid
            ], months=1)

        assert len(result["errors"]) == 1
        assert len(result["applied_adjustments"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulateEndpoint:
    _adj_income = [{"type": "income_change", "pct_change": 10}]

    def test_requires_auth(self, client, app_fixture):
        r = client.post("/scenarios/simulate", json={"adjustments": self._adj_income})
        assert r.status_code == 401

    def test_basic_simulate(self, client, app_fixture):
        h = _auth(client, "e1@sim.test")
        r = client.post("/scenarios/simulate", json={"adjustments": self._adj_income}, headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert "baseline" in d
        assert "scenario" in d
        assert "delta" in d

    def test_response_structure(self, client, app_fixture):
        h = _auth(client, "e2@sim.test")
        r = client.post("/scenarios/simulate", json={"adjustments": self._adj_income}, headers=h)
        d = r.get_json()
        for key in ("baseline", "scenario", "delta", "applied_adjustments",
                    "errors", "analysis_months", "generated_at"):
            assert key in d

    def test_empty_adjustments_returns_400(self, client, app_fixture):
        h = _auth(client, "e3@sim.test")
        r = client.post("/scenarios/simulate", json={"adjustments": []}, headers=h)
        assert r.status_code == 400

    def test_missing_adjustments_returns_400(self, client, app_fixture):
        h = _auth(client, "e4@sim.test")
        r = client.post("/scenarios/simulate", json={}, headers=h)
        assert r.status_code == 400

    def test_too_many_adjustments_returns_400(self, client, app_fixture):
        h = _auth(client, "e5@sim.test")
        adjs = [{"type": "income_change", "pct_change": 1}] * 21
        r = client.post("/scenarios/simulate", json={"adjustments": adjs}, headers=h)
        assert r.status_code == 400

    def test_invalid_months_returns_400(self, client, app_fixture):
        h = _auth(client, "e6@sim.test")
        r = client.post("/scenarios/simulate",
                        json={"adjustments": self._adj_income, "months": 99}, headers=h)
        assert r.status_code == 400

    def test_invalid_anchor_returns_400(self, client, app_fixture):
        h = _auth(client, "e7@sim.test")
        r = client.post("/scenarios/simulate",
                        json={"adjustments": self._adj_income, "anchor": "bad"}, headers=h)
        assert r.status_code == 400

    def test_all_invalid_adjustments_returns_422(self, client, app_fixture):
        h = _auth(client, "e8@sim.test")
        r = client.post("/scenarios/simulate",
                        json={"adjustments": [{"type": "nonsense"}]}, headers=h)
        assert r.status_code == 422

    def test_net_flow_direction_better_on_income_up(self, client, app_fixture):
        h = _auth(client, "e9@sim.test")
        uid = _get_uid(app_fixture, "e9@sim.test")
        _seed_expense(app_fixture, uid, 3000, expense_type="INCOME", days_ago=5)
        _seed_expense(app_fixture, uid, 1000, days_ago=5)

        r = client.post("/scenarios/simulate", json={
            "adjustments": [{"type": "income_change", "pct_change": 20}],
            "months": 1,
        }, headers=h)
        d = r.get_json()
        assert d["delta"]["net_flow_direction"] == "better"

    def test_combine_income_and_category(self, client, app_fixture):
        h = _auth(client, "e10@sim.test")
        uid = _get_uid(app_fixture, "e10@sim.test")
        _seed_expense(app_fixture, uid, 5000, expense_type="INCOME", days_ago=5)
        _seed_expense(app_fixture, uid, 2000, days_ago=5)

        r = client.post("/scenarios/simulate", json={
            "adjustments": [
                {"type": "income_change", "pct_change": 10},
                {"type": "category_change", "category_id": "uncat", "pct_change": -20},
            ],
            "months": 1,
        }, headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert len(d["applied_adjustments"]) == 2
        assert d["delta"]["net_flow_direction"] == "better"

    def test_savings_rate_in_response(self, client, app_fixture):
        h = _auth(client, "e11@sim.test")
        uid = _get_uid(app_fixture, "e11@sim.test")
        _seed_expense(app_fixture, uid, 4000, expense_type="INCOME", days_ago=5)
        _seed_expense(app_fixture, uid, 2000, days_ago=5)

        r = client.post("/scenarios/simulate", json={
            "adjustments": [{"type": "income_change", "pct_change": 0}],
            "months": 1,
        }, headers=h)
        d = r.get_json()
        assert d["baseline"]["savings_rate_pct"] == pytest.approx(50.0, abs=1.0)

    def test_user_isolation(self, client, app_fixture):
        h1 = _auth(client, "iso1@sim.test")
        h2 = _auth(client, "iso2@sim.test")
        uid1 = _get_uid(app_fixture, "iso1@sim.test")
        _seed_expense(app_fixture, uid1, 9000, expense_type="INCOME", days_ago=5)

        r2 = client.post("/scenarios/simulate", json={
            "adjustments": [{"type": "income_change", "pct_change": 10}],
            "months": 1,
        }, headers=h2)
        # User2 has no income, so baseline.income == 0
        assert r2.get_json()["baseline"]["income"] == 0.0

    def test_partial_errors_still_200(self, client, app_fixture):
        """One valid + one invalid adjustment → 200 with errors list."""
        h = _auth(client, "e12@sim.test")
        r = client.post("/scenarios/simulate", json={
            "adjustments": [
                {"type": "income_change", "pct_change": 5},
                {"type": "bad_type"},
            ],
        }, headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert len(d["errors"]) == 1
        assert len(d["applied_adjustments"]) == 1


class TestPresetsEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/scenarios/presets").status_code == 401

    def test_returns_list(self, client, app_fixture):
        h = _auth(client, "p1@sim.test")
        r = client.get("/scenarios/presets", headers=h)
        assert r.status_code == 200
        presets = r.get_json()
        assert isinstance(presets, list)
        assert len(presets) >= 1

    def test_preset_structure(self, client, app_fixture):
        h = _auth(client, "p2@sim.test")
        presets = client.get("/scenarios/presets", headers=h).get_json()
        for p in presets:
            assert "id" in p
            assert "label" in p
            assert "adjustments" in p
            assert isinstance(p["adjustments"], list)
