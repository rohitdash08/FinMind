"""Tests for essential vs discretionary spending breakdown."""
import pytest
from datetime import date
from decimal import Decimal

from app.extensions import db as _db
from app.models import User, Category, CategoryClassification, Expense
from app.services.spending_breakdown import classify_category, get_spending_breakdown


# ── Pure unit tests — no DB needed ────────────────────────────────────────────

class TestClassifyCategory:
    def test_essential_food(self):
        assert classify_category("Food") == "ESSENTIAL"

    def test_essential_transport(self):
        assert classify_category("Transport") == "ESSENTIAL"

    def test_essential_healthcare(self):
        assert classify_category("Healthcare") == "ESSENTIAL"

    def test_discretionary_entertainment(self):
        assert classify_category("Entertainment") == "DISCRETIONARY"

    def test_discretionary_shopping(self):
        assert classify_category("Shopping") == "DISCRETIONARY"

    def test_discretionary_dining(self):
        assert classify_category("Dining Out") == "DISCRETIONARY"

    def test_unknown_returns_uncategorised(self):
        assert classify_category("Miscellaneous") == "UNCATEGORISED"

    def test_user_override_takes_precedence(self):
        result = classify_category("Entertainment", user_overrides={5: "ESSENTIAL"}, category_id=5)
        assert result == "ESSENTIAL"

    def test_no_override_for_other_category(self):
        result = classify_category("Entertainment", user_overrides={99: "ESSENTIAL"}, category_id=5)
        assert result == "DISCRETIONARY"

    def test_case_insensitive(self):
        assert classify_category("FOOD") == "ESSENTIAL"
        assert classify_category("food") == "ESSENTIAL"


# ── DB-backed tests ────────────────────────────────────────────────────────────

def _seed(app_fixture):
    """Seed test data and return (user_id, food_id, entertain_id, misc_id)."""
    with app_fixture.app_context():
        user = User(email="breakdown_test@example.com", password_hash="x", preferred_currency="INR")
        _db.session.add(user)
        _db.session.flush()

        food = Category(user_id=user.id, name="Food")           # ESSENTIAL
        entertain = Category(user_id=user.id, name="Entertainment")  # DISCRETIONARY
        misc = Category(user_id=user.id, name="Misc")           # UNCATEGORISED
        _db.session.add_all([food, entertain, misc])
        _db.session.flush()

        for cat, amt in [(food, 3000), (entertain, 1500), (misc, 500)]:
            _db.session.add(Expense(
                user_id=user.id,
                category_id=cat.id,
                amount=Decimal(str(amt)),
                currency="INR",
                expense_type="EXPENSE",
                spent_at=date(2026, 2, 15),
            ))
        _db.session.commit()
        return user.id, food.id, entertain.id, misc.id


class TestGetSpendingBreakdown:
    def test_totals_correct(self, app_fixture):
        uid, *_ = _seed(app_fixture)
        with app_fixture.app_context():
            result = get_spending_breakdown(uid, _db.session, ym="2026-02")
            assert result["total_spend"] == pytest.approx(5000.0)

    def test_essential_bucket_has_food(self, app_fixture):
        uid, *_ = _seed(app_fixture)
        with app_fixture.app_context():
            result = get_spending_breakdown(uid, _db.session, ym="2026-02")
            names = [c["category_name"] for c in result["essential"]["categories"]]
            assert "Food" in names

    def test_discretionary_bucket_has_entertainment(self, app_fixture):
        uid, *_ = _seed(app_fixture)
        with app_fixture.app_context():
            result = get_spending_breakdown(uid, _db.session, ym="2026-02")
            names = [c["category_name"] for c in result["discretionary"]["categories"]]
            assert "Entertainment" in names

    def test_percentages_sum_to_100(self, app_fixture):
        uid, *_ = _seed(app_fixture)
        with app_fixture.app_context():
            result = get_spending_breakdown(uid, _db.session, ym="2026-02")
            total_pct = (
                result["essential"]["pct_of_total_spend"]
                + result["discretionary"]["pct_of_total_spend"]
                + result["uncategorised"]["pct_of_total_spend"]
            )
            assert total_pct == pytest.approx(100.0, abs=0.5)

    def test_user_override_applied(self, app_fixture):
        uid, food_id, entertain_id, misc_id = _seed(app_fixture)
        with app_fixture.app_context():
            # Override Entertainment → ESSENTIAL
            _db.session.add(CategoryClassification(
                user_id=uid, category_id=entertain_id, classification="ESSENTIAL"
            ))
            _db.session.commit()
            result = get_spending_breakdown(uid, _db.session, ym="2026-02")
            essential_names = [c["category_name"] for c in result["essential"]["categories"]]
            assert "Entertainment" in essential_names
            disc_names = [c["category_name"] for c in result["discretionary"]["categories"]]
            assert "Entertainment" not in disc_names

    def test_income_excluded(self, app_fixture):
        uid, food_id, *_ = _seed(app_fixture)
        with app_fixture.app_context():
            _db.session.add(Expense(
                user_id=uid,
                category_id=food_id,
                amount=Decimal("100000"),
                currency="INR",
                expense_type="INCOME",
                spent_at=date(2026, 2, 15),
            ))
            _db.session.commit()
            result = get_spending_breakdown(uid, _db.session, ym="2026-02")
            assert result["total_spend"] == pytest.approx(5000.0)

    def test_response_shape(self, app_fixture):
        uid, *_ = _seed(app_fixture)
        with app_fixture.app_context():
            result = get_spending_breakdown(uid, _db.session, ym="2026-02")
            for key in ["month", "total_spend", "essential", "discretionary", "uncategorised", "insights"]:
                assert key in result

    def test_insights_not_empty(self, app_fixture):
        uid, *_ = _seed(app_fixture)
        with app_fixture.app_context():
            result = get_spending_breakdown(uid, _db.session, ym="2026-02")
            assert len(result["insights"]) >= 1


class TestBreakdownEndpoints:
    def test_breakdown_requires_auth(self, client):
        resp = client.get("/insights/spending-breakdown")
        assert resp.status_code in (401, 422)

    def test_breakdown_endpoint_exists(self, client):
        resp = client.get("/insights/spending-breakdown")
        assert resp.status_code != 404

    def test_classifications_requires_auth(self, client):
        resp = client.get("/breakdown/classifications")
        assert resp.status_code in (401, 422)

    def test_set_classification_requires_auth(self, client):
        resp = client.post("/breakdown/classifications/1", json={"classification": "ESSENTIAL"})
        assert resp.status_code in (401, 404, 422)


