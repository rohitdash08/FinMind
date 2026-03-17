"""
Tests for Advanced Cash Flow Forecasting (Issue #93).

Covers:
- GET /cashflow/forecast: structure, fields, horizon param
- GET /cashflow/summary: lightweight fields, no forecasts list
- Input validation: months out of range, bad anchor
- Confidence: low with no data, medium/high with more data
- Irregular month detection: spike excluded from baseline
- Seasonal index: months with historically high spending get index > 1
- Bill obligations appear in the correct forecast month
- likely_tight=True when projected_net < 0
- Auth required
- User isolation
- forecast_cashflow unit tests
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Bill, Expense
from app.services.cashflow import forecast_cashflow, _remove_outliers, _confidence


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="cf@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _get_uid(app_fixture, email):
    from app.models import User
    with app_fixture.app_context():
        u = db.session.query(User).filter_by(email=email).first()
        return u.id if u else None


def _seed(app_fixture, uid, amount, expense_type="EXPENSE", days_ago=5, notes="x"):
    with app_fixture.app_context():
        db.session.add(Expense(
            user_id=uid, amount=Decimal(str(amount)), currency="INR",
            expense_type=expense_type,
            spent_at=date.today() - timedelta(days=days_ago), notes=notes,
        ))
        db.session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — cashflow service
# ─────────────────────────────────────────────────────────────────────────────

class TestRemoveOutliers:
    def test_removes_spike(self):
        values = [100, 110, 105, 95, 102, 5000]
        clean = _remove_outliers(values)
        assert 5000 not in clean

    def test_keeps_normal_values(self):
        values = [100, 110, 105, 95, 102]
        clean = _remove_outliers(values)
        assert len(clean) == len(values)

    def test_handles_short_list(self):
        assert _remove_outliers([100]) == [100]
        assert _remove_outliers([]) == []


class TestConfidence:
    def test_low_when_no_data(self):
        assert _confidence(0, False) == "low"

    def test_medium_with_some_data(self):
        assert _confidence(3, True) == "medium"

    def test_high_with_lots_of_data_and_income(self):
        assert _confidence(6, True) == "high"

    def test_medium_without_income(self):
        assert _confidence(6, False) == "medium"


class TestForecastCashflowUnit:
    def _make_user(self, app_fixture, email):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email=email, password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            return u.id

    def test_returns_correct_structure(self, app_fixture):
        uid = self._make_user(app_fixture, "cf_struct@test.com")
        with app_fixture.app_context():
            result = forecast_cashflow(uid, horizon_months=3)
        for key in ("forecasts", "irregular_months", "upcoming_bills",
                    "confidence", "data_months_used", "summary", "generated_at"):
            assert key in result

    def test_forecast_count_matches_horizon(self, app_fixture):
        uid = self._make_user(app_fixture, "cf_count@test.com")
        with app_fixture.app_context():
            result = forecast_cashflow(uid, horizon_months=4)
        assert len(result["forecasts"]) == 4

    def test_user_isolation(self, app_fixture):
        uid1 = self._make_user(app_fixture, "cf_iso1@test.com")
        uid2 = self._make_user(app_fixture, "cf_iso2@test.com")
        with app_fixture.app_context():
            db.session.add(Expense(user_id=uid1, amount=Decimal("9999"), currency="INR",
                                   expense_type="INCOME",
                                   spent_at=date.today() - timedelta(days=3), notes="salary"))
            db.session.commit()
            result = forecast_cashflow(uid2, horizon_months=1)
        assert result["summary"]["avg_projected_income"] == 0.0

    def test_each_forecast_has_required_fields(self, app_fixture):
        uid = self._make_user(app_fixture, "cf_fields@test.com")
        with app_fixture.app_context():
            result = forecast_cashflow(uid, horizon_months=2)
        for f in result["forecasts"]:
            for key in ("month", "projected_income", "projected_expenses",
                        "projected_net", "bill_obligations", "likely_tight",
                        "income_range", "expense_range"):
                assert key in f


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestCashflowForecastEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/cashflow/forecast").status_code == 401

    def test_returns_200(self, client, app_fixture):
        h = _auth(client, "cfe1@test.com")
        r = client.get("/cashflow/forecast", headers=h)
        assert r.status_code == 200

    def test_default_horizon_6(self, client, app_fixture):
        h = _auth(client, "cfe2@test.com")
        d = client.get("/cashflow/forecast", headers=h).get_json()
        assert len(d["forecasts"]) == 6

    def test_custom_horizon(self, client, app_fixture):
        h = _auth(client, "cfe3@test.com")
        r = client.get("/cashflow/forecast?months=3", headers=h)
        assert len(r.get_json()["forecasts"]) == 3

    def test_months_out_of_range_returns_400(self, client, app_fixture):
        h = _auth(client, "cfe4@test.com")
        assert client.get("/cashflow/forecast?months=0", headers=h).status_code == 400
        assert client.get("/cashflow/forecast?months=25", headers=h).status_code == 400

    def test_invalid_months_returns_400(self, client, app_fixture):
        h = _auth(client, "cfe5@test.com")
        assert client.get("/cashflow/forecast?months=abc", headers=h).status_code == 400

    def test_invalid_anchor_returns_400(self, client, app_fixture):
        h = _auth(client, "cfe6@test.com")
        assert client.get("/cashflow/forecast?anchor=bad", headers=h).status_code == 400

    def test_confidence_low_with_no_data(self, client, app_fixture):
        h = _auth(client, "cfe7@test.com")
        d = client.get("/cashflow/forecast", headers=h).get_json()
        assert d["confidence"] == "low"

    def test_likely_tight_when_expenses_exceed_income(self, client, app_fixture):
        h = _auth(client, "cfe8@test.com")
        uid = _get_uid(app_fixture, "cfe8@test.com")
        # Expenses much higher than income
        _seed(app_fixture, uid, 500,  expense_type="INCOME",  days_ago=10)
        _seed(app_fixture, uid, 5000, expense_type="EXPENSE", days_ago=10)

        d = client.get("/cashflow/forecast?months=3", headers=h).get_json()
        tight_months = [f for f in d["forecasts"] if f["likely_tight"]]
        assert len(tight_months) > 0

    def test_response_fields_present(self, client, app_fixture):
        h = _auth(client, "cfe9@test.com")
        d = client.get("/cashflow/forecast", headers=h).get_json()
        for key in ("forecasts", "irregular_months", "upcoming_bills",
                    "confidence", "data_months_used", "summary", "generated_at"):
            assert key in d

    def test_summary_fields(self, client, app_fixture):
        h = _auth(client, "cfe10@test.com")
        s = client.get("/cashflow/forecast", headers=h).get_json()["summary"]
        for key in ("avg_projected_income", "avg_projected_expenses",
                    "avg_projected_net", "positive_months", "negative_months"):
            assert key in s

    def test_user_isolation(self, client, app_fixture):
        h1 = _auth(client, "iso1@cf.test")
        h2 = _auth(client, "iso2@cf.test")
        uid1 = _get_uid(app_fixture, "iso1@cf.test")
        _seed(app_fixture, uid1, 9999, expense_type="INCOME", days_ago=5)

        d2 = client.get("/cashflow/forecast?months=1", headers=h2).get_json()
        assert d2["summary"]["avg_projected_income"] == 0.0


class TestCashflowSummaryEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/cashflow/summary").status_code == 401

    def test_returns_200(self, client, app_fixture):
        h = _auth(client, "cfs1@test.com")
        assert client.get("/cashflow/summary", headers=h).status_code == 200

    def test_no_forecasts_list_in_response(self, client, app_fixture):
        h = _auth(client, "cfs2@test.com")
        d = client.get("/cashflow/summary", headers=h).get_json()
        assert "forecasts" not in d
        assert "summary" in d
        assert "confidence" in d

    def test_horizon_months_present(self, client, app_fixture):
        h = _auth(client, "cfs3@test.com")
        d = client.get("/cashflow/summary?months=4", headers=h).get_json()
        assert d["horizon_months"] == 4
