"""Tests for lifestyle inflation detection service."""
import pytest
from datetime import date
from decimal import Decimal

from flask_jwt_extended import create_access_token

from app.extensions import db as _db
from app.models import User, Category, Expense
from app.services.inflation import (
    detect_lifestyle_inflation,
    _ym_range,
    _consecutive_increases,
    _pct_change,
)


# ── Helper unit tests ─────────────────────────────────────────────────────────

class TestYmRange:
    def test_returns_correct_count(self):
        ref = date(2026, 3, 15)
        result = _ym_range(ref, 3)
        assert len(result) == 3

    def test_excludes_current_month(self):
        ref = date(2026, 3, 15)
        result = _ym_range(ref, 3)
        assert "2026-03" not in result

    def test_oldest_first(self):
        ref = date(2026, 3, 15)
        result = _ym_range(ref, 3)
        assert result == ["2025-12", "2026-01", "2026-02"]

    def test_wraps_year_correctly(self):
        ref = date(2026, 2, 1)
        result = _ym_range(ref, 2)
        assert "2025-12" in result
        assert "2026-01" in result


class TestConsecutiveIncreases:
    def test_all_increasing(self):
        assert _consecutive_increases([100, 200, 300, 400]) == 3

    def test_no_increases(self):
        assert _consecutive_increases([400, 300, 200, 100]) == 0

    def test_trailing_increases_only(self):
        assert _consecutive_increases([400, 100, 200, 300]) == 2

    def test_single_value(self):
        assert _consecutive_increases([100]) == 0


class TestPctChange:
    def test_positive_change(self):
        assert _pct_change(100, 150) == pytest.approx(50.0)

    def test_negative_change(self):
        assert _pct_change(200, 100) == pytest.approx(-50.0)

    def test_zero_base_returns_none(self):
        assert _pct_change(0, 100) is None

    def test_no_change(self):
        assert _pct_change(100, 100) == pytest.approx(0.0)


# ── Service integration tests ─────────────────────────────────────────────────

class TestDetectLifestyleInflation:
    def _seed_data(self, app_fixture):
        """Create user + category + escalating expenses across 3 months."""
        with app_fixture.app_context():
            user = User(
                email="inflation_test@example.com",
                password_hash="x",
                preferred_currency="INR",
            )
            _db.session.add(user)
            _db.session.flush()
            food = Category(user_id=user.id, name="Food")
            _db.session.add(food)
            _db.session.flush()

            # Escalating food spend: Jan=1000, Feb=1300, Mar=1700 (inflating)
            for ym, amount in [("2026-01", 1000), ("2026-02", 1300), ("2026-03", 1700)]:
                y, m = map(int, ym.split("-"))
                _db.session.add(Expense(
                    user_id=user.id,
                    category_id=food.id,
                    amount=Decimal(str(amount)),
                    currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date(y, m, 15),
                ))
            _db.session.commit()
            return user.id, food.id

    def test_detects_inflating_category(self, app_fixture):
        uid, _ = self._seed_data(app_fixture)
        with app_fixture.app_context():
            result = detect_lifestyle_inflation(
                uid, _db.session, months=3, reference_date=date(2026, 4, 1)
            )
            inflating = [c for c in result["inflating_categories"] if c["status"] == "INFLATING"]
            assert len(inflating) >= 1
            assert any(c["category_name"] == "Food" for c in inflating)

    def test_result_shape(self, app_fixture):
        uid, _ = self._seed_data(app_fixture)
        with app_fixture.app_context():
            result = detect_lifestyle_inflation(
                uid, _db.session, months=3, reference_date=date(2026, 4, 1)
            )
            for key in [
                "period_months", "months_analysed", "inflation_score",
                "overall_trend", "monthly_totals", "inflating_categories", "insights",
            ]:
                assert key in result, f"missing key: {key}"

    def test_inflation_score_range(self, app_fixture):
        uid, _ = self._seed_data(app_fixture)
        with app_fixture.app_context():
            result = detect_lifestyle_inflation(
                uid, _db.session, months=3, reference_date=date(2026, 4, 1)
            )
            assert 0 <= result["inflation_score"] <= 100

    def test_no_data_returns_flat_or_insufficient(self, app_fixture):
        with app_fixture.app_context():
            user = User(
                email="empty_inflation@example.com",
                password_hash="x",
                preferred_currency="INR",
            )
            _db.session.add(user)
            _db.session.commit()
            result = detect_lifestyle_inflation(
                user.id, _db.session, months=3, reference_date=date(2026, 4, 1)
            )
            assert result["overall_trend"] in ("FLAT", "INSUFFICIENT_DATA")

    def test_income_not_counted_as_spend(self, app_fixture):
        uid, food_id = self._seed_data(app_fixture)
        with app_fixture.app_context():
            # Add large income entries — should NOT inflate spend totals
            for ym in ["2026-01", "2026-02", "2026-03"]:
                y, m = map(int, ym.split("-"))
                _db.session.add(Expense(
                    user_id=uid,
                    category_id=food_id,
                    amount=Decimal("50000"),
                    currency="INR",
                    expense_type="INCOME",
                    spent_at=date(y, m, 15),
                ))
            _db.session.commit()
            result = detect_lifestyle_inflation(
                uid, _db.session, months=3, reference_date=date(2026, 4, 1)
            )
            # Food spend should still be 1000/1300/1700, not inflated by income
            food_cat = next(
                (c for c in result["inflating_categories"] if c["category_name"] == "Food"),
                None,
            )
            assert food_cat is not None
            assert max(food_cat["monthly_spend"]) < 10000

    def test_insights_list_not_empty(self, app_fixture):
        uid, _ = self._seed_data(app_fixture)
        with app_fixture.app_context():
            result = detect_lifestyle_inflation(
                uid, _db.session, months=3, reference_date=date(2026, 4, 1)
            )
            assert isinstance(result["insights"], list)
            assert len(result["insights"]) >= 1

    def test_months_clamped(self, app_fixture):
        uid, _ = self._seed_data(app_fixture)
        with app_fixture.app_context():
            result = detect_lifestyle_inflation(
                uid, _db.session, months=99, reference_date=date(2026, 4, 1)
            )
            assert result["period_months"] == 12


# ── Endpoint tests ─────────────────────────────────────────────────────────────

@pytest.fixture()
def jwt_auth_header(app_fixture):
    """Return an Authorization header using a directly-created JWT (no Redis login)."""
    with app_fixture.app_context():
        # Create a test user
        user = User(
            email="jwt_test@example.com",
            password_hash="x",
            preferred_currency="INR",
        )
        _db.session.add(user)
        _db.session.commit()
        token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


class TestInflationEndpoint:
    def test_endpoint_requires_auth(self, client):
        resp = client.get("/insights/inflation")
        assert resp.status_code in (401, 422)

    def test_endpoint_exists(self, client):
        resp = client.get("/insights/inflation")
        assert resp.status_code != 404

    def test_endpoint_returns_json_with_auth(self, client, jwt_auth_header, monkeypatch):
        monkeypatch.setattr("app.routes.insights.cache_get", lambda k: None)
        monkeypatch.setattr("app.routes.insights.cache_set", lambda k, v, **kw: None)
        resp = client.get("/insights/inflation?months=3", headers=jwt_auth_header)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert "inflation_score" in payload
        assert "overall_trend" in payload
        assert "inflating_categories" in payload
        assert "insights" in payload

    def test_endpoint_months_param(self, client, jwt_auth_header, monkeypatch):
        monkeypatch.setattr("app.routes.insights.cache_get", lambda k: None)
        monkeypatch.setattr("app.routes.insights.cache_set", lambda k, v, **kw: None)
        resp = client.get("/insights/inflation?months=3", headers=jwt_auth_header)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["period_months"] == 3

    def test_endpoint_clamps_months(self, client, jwt_auth_header, monkeypatch):
        monkeypatch.setattr("app.routes.insights.cache_get", lambda k: None)
        monkeypatch.setattr("app.routes.insights.cache_set", lambda k, v, **kw: None)
        resp = client.get("/insights/inflation?months=99", headers=jwt_auth_header)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["period_months"] == 12
