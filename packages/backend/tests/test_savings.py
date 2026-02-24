"""Tests for savings opportunity detection engine."""
import pytest
from datetime import date
from decimal import Decimal

from app import create_app
from app.config import Settings
from app.extensions import db as _db
from app.models import User, Category, Expense
from app.services.savings import (
    detect_savings_opportunities,
    _prior_months,
    _category_spend_for_month,
)


@pytest.fixture
def app():
    settings = Settings(
        database_url="sqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        jwt_secret="test-secret",
    )
    application = create_app(settings)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# ── Helper tests ──────────────────────────────────────────────────────────────

class TestPriorMonths:
    def test_returns_correct_count(self):
        ref = date(2026, 3, 15)
        result = _prior_months(ref, 3)
        assert len(result) == 3

    def test_excludes_current_month(self):
        ref = date(2026, 3, 15)
        result = _prior_months(ref, 3)
        assert (2026, 3) not in result

    def test_wraps_year(self):
        ref = date(2026, 2, 10)
        result = _prior_months(ref, 2)
        assert (2025, 12) in result


# ── Service integration tests ─────────────────────────────────────────────────

class TestDetectSavingsOpportunities:
    def _seed(self, app, db):
        with app.app_context():
            user = User(email="saver@example.com", password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.flush()
            food = Category(user_id=user.id, name="Food")
            entertainment = Category(user_id=user.id, name="Entertainment")
            _db.session.add_all([food, entertainment])
            _db.session.flush()

            # Food: historical avg=2000, current=3000 (50% above — HIGH_SPEND)
            for ym, amt in [("2025-11", 2000), ("2025-12", 2000), ("2026-01", 2000)]:
                y, m = map(int, ym.split("-"))
                _db.session.add(Expense(
                    user_id=user.id, category_id=food.id,
                    amount=Decimal(str(amt)), currency="INR",
                    expense_type="EXPENSE", spent_at=date(y, m, 15),
                ))
            # Current month (Feb 2026): food = 3000
            _db.session.add(Expense(
                user_id=user.id, category_id=food.id,
                amount=Decimal("3000"), currency="INR",
                expense_type="EXPENSE", spent_at=date(2026, 2, 15),
            ))
            # Entertainment: historical avg=500, current=550 (10% above — not flagged)
            for ym, amt in [("2025-11", 500), ("2025-12", 500), ("2026-01", 500)]:
                y, m = map(int, ym.split("-"))
                _db.session.add(Expense(
                    user_id=user.id, category_id=entertainment.id,
                    amount=Decimal(str(amt)), currency="INR",
                    expense_type="EXPENSE", spent_at=date(y, m, 15),
                ))
            _db.session.add(Expense(
                user_id=user.id, category_id=entertainment.id,
                amount=Decimal("550"), currency="INR",
                expense_type="EXPENSE", spent_at=date(2026, 2, 15),
            ))
            _db.session.commit()
            return user.id

    def test_flags_high_spend_category(self, app, db):
        uid = self._seed(app, db)
        with app.app_context():
            result = detect_savings_opportunities(uid, _db.session, months=3, reference_date=date(2026, 2, 15))
            names = [o["category_name"] for o in result["opportunities"]]
            assert "Food" in names

    def test_does_not_flag_minor_overspend(self, app, db):
        uid = self._seed(app, db)
        with app.app_context():
            result = detect_savings_opportunities(uid, _db.session, months=3, reference_date=date(2026, 2, 15))
            names = [o["category_name"] for o in result["opportunities"]]
            # Entertainment only 10% above — below 20% threshold
            assert "Entertainment" not in names

    def test_response_shape(self, app, db):
        uid = self._seed(app, db)
        with app.app_context():
            result = detect_savings_opportunities(uid, _db.session, months=3, reference_date=date(2026, 2, 15))
            for key in ["reference_month", "comparison_months", "total_current_spend",
                        "total_potential_savings", "opportunities", "insights"]:
                assert key in result

    def test_potential_savings_calculated(self, app, db):
        uid = self._seed(app, db)
        with app.app_context():
            result = detect_savings_opportunities(uid, _db.session, months=3, reference_date=date(2026, 2, 15))
            assert result["total_potential_savings"] > 0

    def test_income_excluded(self, app, db):
        uid = self._seed(app, db)
        with app.app_context():
            # Add large income — should not affect spend totals
            _db.session.add(Expense(
                user_id=uid, category_id=None,
                amount=Decimal("100000"), currency="INR",
                expense_type="INCOME", spent_at=date(2026, 2, 15),
            ))
            _db.session.commit()
            result = detect_savings_opportunities(uid, _db.session, months=3, reference_date=date(2026, 2, 15))
            assert result["total_current_spend"] < 10000

    def test_no_spend_returns_empty_opportunities(self, app, db):
        with app.app_context():
            _db.create_all()
            user = User(email="empty2@example.com", password_hash="x", preferred_currency="INR")
            _db.session.add(user)
            _db.session.commit()
            result = detect_savings_opportunities(user.id, _db.session, months=3, reference_date=date(2026, 2, 15))
            assert result["opportunities"] == []
            assert len(result["insights"]) >= 1

    def test_insights_not_empty(self, app, db):
        uid = self._seed(app, db)
        with app.app_context():
            result = detect_savings_opportunities(uid, _db.session, months=3, reference_date=date(2026, 2, 15))
            assert isinstance(result["insights"], list) and len(result["insights"]) >= 1

    def test_opportunity_has_recommendation(self, app, db):
        uid = self._seed(app, db)
        with app.app_context():
            result = detect_savings_opportunities(uid, _db.session, months=3, reference_date=date(2026, 2, 15))
            for opp in result["opportunities"]:
                assert "recommendation" in opp
                assert len(opp["recommendation"]) > 10


class TestSavingsEndpoint:
    def test_requires_auth(self, client):
        resp = client.get("/insights/savings")
        assert resp.status_code in (401, 422)

    def test_endpoint_exists(self, client):
        resp = client.get("/insights/savings")
        assert resp.status_code != 404

    def test_months_param_accepted(self, client):
        resp = client.get("/insights/savings?months=6")
        assert resp.status_code in (200, 401, 422)
