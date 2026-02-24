"""Tests for category overspend early warning system."""
import pytest
import fakeredis
from unittest.mock import patch
from datetime import date
from decimal import Decimal

from app.extensions import db as _db
from app.models import User, Category, CategoryBudget, Expense
from app.services.overspend import check_category_warnings


# ── Redis mock (no real Redis in CI) ─────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_redis():
    """Replace the global redis_client with fakeredis for all tests."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    with (
        patch("app.extensions.redis_client", fake),
        patch("app.routes.auth.redis_client", fake),
        patch("app.services.cache.redis_client", fake),
    ):
        yield fake


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_data(app_fixture):
    """Create a user, categories, budgets, and expenses for overspend tests."""
    with app_fixture.app_context():
        user = User(
            email="overspend@example.com",
            password_hash="hashed",
            preferred_currency="INR",
        )
        _db.session.add(user)
        _db.session.flush()

        food = Category(user_id=user.id, name="Food")
        shopping = Category(user_id=user.id, name="Shopping")
        transport = Category(user_id=user.id, name="Transport")
        _db.session.add_all([food, shopping, transport])
        _db.session.flush()

        # Budgets: Food=5000, Shopping=3000, Transport=2000
        _db.session.add(CategoryBudget(
            user_id=user.id, category_id=food.id,
            monthly_limit=Decimal("5000"), currency="INR"
        ))
        _db.session.add(CategoryBudget(
            user_id=user.id, category_id=shopping.id,
            monthly_limit=Decimal("3000"), currency="INR"
        ))
        _db.session.add(CategoryBudget(
            user_id=user.id, category_id=transport.id,
            monthly_limit=Decimal("2000"), currency="INR"
        ))

        today = date.today()
        # Food: 4200 spent (84% — WARNING)
        _db.session.add(Expense(
            user_id=user.id, category_id=food.id,
            amount=Decimal("4200"), currency="INR",
            expense_type="EXPENSE", spent_at=today
        ))
        # Shopping: 3100 spent (103% — EXCEEDED)
        _db.session.add(Expense(
            user_id=user.id, category_id=shopping.id,
            amount=Decimal("3100"), currency="INR",
            expense_type="EXPENSE", spent_at=today
        ))
        # Transport: 500 spent (25% — no warning)
        _db.session.add(Expense(
            user_id=user.id, category_id=transport.id,
            amount=Decimal("500"), currency="INR",
            expense_type="EXPENSE", spent_at=today
        ))

        _db.session.commit()
        return {
            "user_id": user.id,
            "food_id": food.id,
            "shopping_id": shopping.id,
            "transport_id": transport.id,
        }


# ── Unit tests: check_category_warnings ───────────────────────────────────────

class TestCheckCategoryWarnings:
    def test_returns_only_threshold_categories(self, app_fixture, sample_data):
        with app_fixture.app_context():
            warnings = check_category_warnings(sample_data["user_id"], _db.session)
            category_names = [w["category_name"] for w in warnings]
            assert "Shopping" in category_names   # EXCEEDED
            assert "Food" in category_names        # WARNING
            assert "Transport" not in category_names  # under 70%

    def test_exceeded_sorted_first(self, app_fixture, sample_data):
        with app_fixture.app_context():
            warnings = check_category_warnings(sample_data["user_id"], _db.session)
            assert warnings[0]["status"] == "EXCEEDED"

    def test_warning_status_at_70_percent(self, app_fixture, sample_data):
        with app_fixture.app_context():
            warnings = check_category_warnings(sample_data["user_id"], _db.session)
            food_w = next(w for w in warnings if w["category_name"] == "Food")
            assert food_w["status"] == "WARNING"
            assert food_w["pct_used"] >= 0.70

    def test_exceeded_status_at_100_percent(self, app_fixture, sample_data):
        with app_fixture.app_context():
            warnings = check_category_warnings(sample_data["user_id"], _db.session)
            shopping_w = next(w for w in warnings if w["category_name"] == "Shopping")
            assert shopping_w["status"] == "EXCEEDED"
            assert shopping_w["pct_used"] >= 1.0
            assert shopping_w["remaining"] < 0

    def test_income_excluded_from_spend(self, app_fixture, sample_data):
        with app_fixture.app_context():
            # Add income entry for food — should NOT count toward spend
            _db.session.add(Expense(
                user_id=sample_data["user_id"],
                category_id=sample_data["food_id"],
                amount=Decimal("10000"),
                currency="INR",
                expense_type="INCOME",
                spent_at=date.today(),
            ))
            _db.session.commit()
            warnings = check_category_warnings(sample_data["user_id"], _db.session)
            food_w = next(w for w in warnings if w["category_name"] == "Food")
            # Spend should still be 4200, not 14200
            assert food_w["spent"] == pytest.approx(4200.0, abs=0.01)

    def test_no_budgets_returns_empty(self, app_fixture):
        with app_fixture.app_context():
            user = User(
                email="nobudget@example.com",
                password_hash="x",
                preferred_currency="INR",
            )
            _db.session.add(user)
            _db.session.commit()
            warnings = check_category_warnings(user.id, _db.session)
            assert warnings == []

    def test_warning_fields_present(self, app_fixture, sample_data):
        with app_fixture.app_context():
            warnings = check_category_warnings(sample_data["user_id"], _db.session)
            assert len(warnings) > 0
            w = warnings[0]
            for field in [
                "category_id", "category_name", "monthly_limit", "currency",
                "spent", "pct_used", "remaining", "status", "month",
            ]:
                assert field in w, f"missing field: {field}"

    def test_under_threshold_not_included(self, app_fixture, sample_data):
        """Transport at 25% should not appear in warnings."""
        with app_fixture.app_context():
            warnings = check_category_warnings(sample_data["user_id"], _db.session)
            statuses = [w["category_name"] for w in warnings]
            assert "Transport" not in statuses


# ── API tests: /alerts and /budgets endpoints ─────────────────────────────────

class TestBudgetAPI:
    def test_alerts_endpoint_requires_auth(self, client):
        resp = client.get("/alerts/overspend")
        assert resp.status_code in (401, 422)

    def test_budgets_list_requires_auth(self, client):
        resp = client.get("/budgets")
        assert resp.status_code in (401, 422)

    def test_set_budget_requires_auth(self, client):
        resp = client.post("/budgets/1", json={"monthly_limit": 5000})
        assert resp.status_code in (401, 404, 422)

    def test_delete_budget_requires_auth(self, client):
        resp = client.delete("/budgets/1")
        assert resp.status_code in (401, 404, 422)

    def test_alerts_authenticated(self, client, auth_header):
        """Authenticated user gets empty warnings list with no budgets set."""
        resp = client.get("/alerts/overspend", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "count" in data
        assert "warnings" in data
        assert data["count"] == 0
        assert data["warnings"] == []

    def test_budgets_list_authenticated_empty(self, client, auth_header):
        """Authenticated user gets empty budget list initially."""
        resp = client.get("/budgets", headers=auth_header)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_set_and_list_budget(self, client, auth_header):
        """Create a category then set a budget on it."""
        # Create category
        r = client.post("/categories", json={"name": "TestCat"}, headers=auth_header)
        assert r.status_code == 201
        cat_id = r.get_json()["id"]

        # Set budget
        r = client.post(
            f"/budgets/{cat_id}",
            json={"monthly_limit": 5000, "currency": "INR"},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["monthly_limit"] == 5000.0
        assert data["currency"] == "INR"
        assert data["category_id"] == cat_id

        # List budgets
        r = client.get("/budgets", headers=auth_header)
        assert r.status_code == 200
        budgets = r.get_json()
        assert len(budgets) == 1
        assert budgets[0]["category_id"] == cat_id

    def test_update_budget(self, client, auth_header):
        """Update an existing budget."""
        r = client.post("/categories", json={"name": "UpdateCat"}, headers=auth_header)
        cat_id = r.get_json()["id"]

        client.post(f"/budgets/{cat_id}", json={"monthly_limit": 1000}, headers=auth_header)
        r = client.post(f"/budgets/{cat_id}", json={"monthly_limit": 2000}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["monthly_limit"] == 2000.0

    def test_delete_budget(self, client, auth_header):
        """Delete a budget."""
        r = client.post("/categories", json={"name": "DelCat"}, headers=auth_header)
        cat_id = r.get_json()["id"]

        client.post(f"/budgets/{cat_id}", json={"monthly_limit": 1000}, headers=auth_header)

        r = client.delete(f"/budgets/{cat_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["message"] == "deleted"

        # Should be gone
        r = client.get("/budgets", headers=auth_header)
        assert r.get_json() == []

    def test_alerts_shows_overspend(self, client, auth_header):
        """Set a tiny budget, add an expense exceeding it, check alerts."""
        # Create category
        r = client.post("/categories", json={"name": "AlertCat"}, headers=auth_header)
        cat_id = r.get_json()["id"]

        # Set budget of 100 INR
        client.post(
            f"/budgets/{cat_id}",
            json={"monthly_limit": 100, "currency": "INR"},
            headers=auth_header,
        )

        # Add an expense of 90 (90% — WARNING)
        client.post(
            "/expenses",
            json={
                "amount": 90,
                "currency": "INR",
                "category_id": cat_id,
                "expense_type": "EXPENSE",
                "description": "test expense",
                "spent_at": date.today().isoformat(),
            },
            headers=auth_header,
        )

        r = client.get("/alerts/overspend", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["count"] >= 1
        names = [w["category_name"] for w in data["warnings"]]
        assert "AlertCat" in names

    def test_set_budget_invalid_limit(self, client, auth_header):
        """Reject non-positive monthly_limit."""
        r = client.post("/categories", json={"name": "BadLimitCat"}, headers=auth_header)
        cat_id = r.get_json()["id"]
        r = client.post(f"/budgets/{cat_id}", json={"monthly_limit": -100}, headers=auth_header)
        assert r.status_code == 400

    def test_set_budget_missing_limit(self, client, auth_header):
        """Reject missing monthly_limit."""
        r = client.post("/categories", json={"name": "NoLimitCat"}, headers=auth_header)
        cat_id = r.get_json()["id"]
        r = client.post(f"/budgets/{cat_id}", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_delete_nonexistent_budget(self, client, auth_header):
        """Delete non-existent budget returns 404."""
        r = client.delete("/budgets/999999", headers=auth_header)
        assert r.status_code == 404
