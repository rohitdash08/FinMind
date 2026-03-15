"""Tests for category overspend early warning system (Issue #117).

Covers:
  - Budget CRUD operations
  - Spending calculations
  - Budget status checking
  - Alert generation
  - Alert management
  - Spending forecast
  - API endpoint testing
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from app.models import Category, CategoryBudget, Expense, OverspendAlert
from app.services.overspend import (
    create_budget,
    get_budgets,
    update_budget,
    delete_budget,
    get_category_spending,
    check_budget_status,
    generate_alerts,
    get_alerts,
    mark_alert_read,
    mark_all_alerts_read,
    get_spending_forecast,
)
from app.extensions import db


def _create_category(user_id, name="Food"):
    """Helper to create a category."""
    cat = Category(user_id=user_id, name=name)
    db.session.add(cat)
    db.session.commit()
    return cat


def _create_expense(user_id, category_id, amount, spent_at=None):
    """Helper to create an expense."""
    exp = Expense(
        user_id=user_id,
        category_id=category_id,
        amount=Decimal(str(amount)),
        currency="INR",
        expense_type="EXPENSE",
        notes="test expense",
        spent_at=spent_at or date.today(),
    )
    db.session.add(exp)
    db.session.commit()
    return exp


# ─── Budget CRUD tests ──────────────────────────────────────────────────


class TestBudgetCRUD:
    def test_create_budget(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            result = create_budget(1, cat.id, 5000.00)
            assert result is not None
            assert result["monthly_limit"] == 5000.00
            assert result["warning_threshold"] == 80.00
            assert result["critical_threshold"] == 95.00
            assert result["is_active"] is True

    def test_create_budget_invalid_category(self, app_fixture):
        with app_fixture.app_context():
            result = create_budget(1, 999, 5000.00)
            assert result is None

    def test_create_budget_updates_existing(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 5000.00)
            result = create_budget(1, cat.id, 8000.00)
            assert result["monthly_limit"] == 8000.00

    def test_create_budget_custom_thresholds(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            result = create_budget(
                1, cat.id, 5000.00,
                warning_threshold=70.0,
                critical_threshold=90.0,
            )
            assert result["warning_threshold"] == 70.00
            assert result["critical_threshold"] == 90.00

    def test_get_budgets(self, app_fixture):
        with app_fixture.app_context():
            cat1 = _create_category(1, "Food")
            cat2 = _create_category(1, "Transport")
            create_budget(1, cat1.id, 5000.00)
            create_budget(1, cat2.id, 3000.00)
            budgets = get_budgets(1)
            assert len(budgets) == 2

    def test_get_budgets_active_only(self, app_fixture):
        with app_fixture.app_context():
            cat1 = _create_category(1, "Food")
            cat2 = _create_category(1, "Transport")
            create_budget(1, cat1.id, 5000.00)
            b2 = create_budget(1, cat2.id, 3000.00)
            delete_budget(1, b2["id"])
            active = get_budgets(1, active_only=True)
            assert len(active) == 1
            all_budgets = get_budgets(1, active_only=False)
            assert len(all_budgets) == 2

    def test_update_budget(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            b = create_budget(1, cat.id, 5000.00)
            updated = update_budget(1, b["id"], {"monthly_limit": 7000.00})
            assert updated["monthly_limit"] == 7000.00

    def test_update_budget_not_found(self, app_fixture):
        with app_fixture.app_context():
            result = update_budget(1, 999, {"monthly_limit": 7000.00})
            assert result is None

    def test_delete_budget(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            b = create_budget(1, cat.id, 5000.00)
            assert delete_budget(1, b["id"]) is True
            active = get_budgets(1)
            assert len(active) == 0

    def test_delete_budget_not_found(self, app_fixture):
        with app_fixture.app_context():
            assert delete_budget(1, 999) is False


# ─── Spending calculation tests ──────────────────────────────────────────


class TestSpendingCalculation:
    def test_get_category_spending(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            today = date.today()
            _create_expense(1, cat.id, 1000, today)
            _create_expense(1, cat.id, 2000, today)
            start = today.replace(day=1)
            end = today
            total = get_category_spending(1, cat.id, start, end)
            assert total == Decimal("3000")

    def test_get_spending_no_expenses(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            today = date.today()
            total = get_category_spending(1, cat.id, today, today)
            assert total == Decimal("0")

    def test_spending_excludes_other_categories(self, app_fixture):
        with app_fixture.app_context():
            cat1 = _create_category(1, "Food")
            cat2 = _create_category(1, "Transport")
            today = date.today()
            _create_expense(1, cat1.id, 1000, today)
            _create_expense(1, cat2.id, 2000, today)
            total = get_category_spending(1, cat1.id, today, today)
            assert total == Decimal("1000")


# ─── Budget status tests ────────────────────────────────────────────────


class TestBudgetStatus:
    def test_normal_status(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 10000.00)
            _create_expense(1, cat.id, 1000, date.today())
            statuses = check_budget_status(1)
            assert len(statuses) == 1
            assert statuses[0]["alert_level"] == "normal"
            assert statuses[0]["percentage_used"] <= 80

    def test_warning_status(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 1000.00)
            _create_expense(1, cat.id, 850, date.today())
            statuses = check_budget_status(1)
            assert statuses[0]["alert_level"] == "warning"

    def test_critical_status(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 1000.00)
            _create_expense(1, cat.id, 960, date.today())
            statuses = check_budget_status(1)
            assert statuses[0]["alert_level"] == "critical"

    def test_exceeded_status(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 1000.00)
            _create_expense(1, cat.id, 1100, date.today())
            statuses = check_budget_status(1)
            assert statuses[0]["alert_level"] == "exceeded"

    def test_status_includes_daily_safe_spend(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 10000.00)
            _create_expense(1, cat.id, 3000, date.today())
            statuses = check_budget_status(1)
            assert "daily_safe_spend" in statuses[0]
            assert statuses[0]["daily_safe_spend"] >= 0

    def test_status_includes_remaining(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 5000.00)
            _create_expense(1, cat.id, 2000, date.today())
            statuses = check_budget_status(1)
            assert statuses[0]["remaining"] == 3000.00


# ─── Alert generation tests ─────────────────────────────────────────────


class TestAlertGeneration:
    def test_generates_warning_alert(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 1000.00)
            _create_expense(1, cat.id, 850, date.today())
            alerts = generate_alerts(1)
            assert len(alerts) == 1
            assert alerts[0]["alert_type"] == "warning"

    def test_no_duplicate_alerts(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 1000.00)
            _create_expense(1, cat.id, 850, date.today())
            alerts1 = generate_alerts(1)
            assert len(alerts1) == 1
            alerts2 = generate_alerts(1)
            assert len(alerts2) == 0

    def test_no_alert_when_normal(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 10000.00)
            _create_expense(1, cat.id, 100, date.today())
            alerts = generate_alerts(1)
            assert len(alerts) == 0

    def test_exceeded_alert(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 1000.00)
            _create_expense(1, cat.id, 1100, date.today())
            alerts = generate_alerts(1)
            assert len(alerts) == 1
            assert alerts[0]["alert_type"] == "exceeded"


# ─── Alert management tests ─────────────────────────────────────────────


class TestAlertManagement:
    def _seed_alert(self, user_id=1):
        cat = _create_category(user_id)
        budget = CategoryBudget(
            user_id=user_id, category_id=cat.id,
            monthly_limit=Decimal("1000"), currency="INR",
            warning_threshold=Decimal("80"), critical_threshold=Decimal("95"),
        )
        db.session.add(budget)
        db.session.commit()
        today = date.today()
        alert = OverspendAlert(
            user_id=user_id, category_id=cat.id, budget_id=budget.id,
            alert_type="warning", spent_amount=Decimal("850"),
            budget_limit=Decimal("1000"), percentage_used=Decimal("85.00"),
            period_start=today.replace(day=1), period_end=today,
        )
        db.session.add(alert)
        db.session.commit()
        return alert.id

    def test_get_alerts(self, app_fixture):
        with app_fixture.app_context():
            self._seed_alert()
            alerts = get_alerts(1)
            assert len(alerts) == 1

    def test_get_unread_alerts(self, app_fixture):
        with app_fixture.app_context():
            self._seed_alert()
            alerts = get_alerts(1, unread_only=True)
            assert len(alerts) == 1

    def test_mark_alert_read(self, app_fixture):
        with app_fixture.app_context():
            aid = self._seed_alert()
            assert mark_alert_read(1, aid) is True
            alerts = get_alerts(1, unread_only=True)
            assert len(alerts) == 0

    def test_mark_alert_read_not_found(self, app_fixture):
        with app_fixture.app_context():
            assert mark_alert_read(1, 999) is False

    def test_mark_all_read(self, app_fixture):
        with app_fixture.app_context():
            self._seed_alert()
            self._seed_alert()
            count = mark_all_alerts_read(1)
            assert count == 2
            alerts = get_alerts(1, unread_only=True)
            assert len(alerts) == 0


# ─── Spending forecast tests ────────────────────────────────────────────


class TestSpendingForecast:
    def test_forecast_returns_results(self, app_fixture):
        with app_fixture.app_context():
            cat = _create_category(1)
            create_budget(1, cat.id, 5000.00)
            _create_expense(1, cat.id, 2000, date.today())
            forecasts = get_spending_forecast(1)
            assert len(forecasts) == 1
            assert "projected_total" in forecasts[0]
            assert "will_exceed" in forecasts[0]
            assert "daily_rate" in forecasts[0]

    def test_forecast_empty(self, app_fixture):
        with app_fixture.app_context():
            forecasts = get_spending_forecast(999)
            assert forecasts == []


# ─── API tests ──────────────────────────────────────────────────────────


class TestBudgetAPI:
    def _create_cat_via_api(self, client, auth_header, name="Food"):
        resp = client.post(
            "/categories", json={"name": name}, headers=auth_header
        )
        return resp.get_json()["id"]

    def test_create_budget_endpoint(self, client, auth_header):
        cat_id = self._create_cat_via_api(client, auth_header)
        resp = client.post("/budgets", json={
            "category_id": cat_id,
            "monthly_limit": 5000,
        }, headers=auth_header)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["monthly_limit"] == 5000.0

    def test_create_budget_missing_fields(self, client, auth_header):
        resp = client.post("/budgets", json={}, headers=auth_header)
        assert resp.status_code == 400

    def test_create_budget_invalid_limit(self, client, auth_header):
        cat_id = self._create_cat_via_api(client, auth_header)
        resp = client.post("/budgets", json={
            "category_id": cat_id,
            "monthly_limit": -100,
        }, headers=auth_header)
        assert resp.status_code == 400

    def test_list_budgets_endpoint(self, client, auth_header):
        resp = client.get("/budgets", headers=auth_header)
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_budget_not_found(self, client, auth_header):
        resp = client.get("/budgets/999", headers=auth_header)
        assert resp.status_code == 404

    def test_update_budget_endpoint(self, client, auth_header):
        cat_id = self._create_cat_via_api(client, auth_header)
        resp = client.post("/budgets", json={
            "category_id": cat_id,
            "monthly_limit": 5000,
        }, headers=auth_header)
        budget_id = resp.get_json()["id"]
        resp = client.patch(f"/budgets/{budget_id}", json={
            "monthly_limit": 7000,
        }, headers=auth_header)
        assert resp.status_code == 200
        assert resp.get_json()["monthly_limit"] == 7000.0

    def test_delete_budget_endpoint(self, client, auth_header):
        cat_id = self._create_cat_via_api(client, auth_header)
        resp = client.post("/budgets", json={
            "category_id": cat_id,
            "monthly_limit": 5000,
        }, headers=auth_header)
        budget_id = resp.get_json()["id"]
        resp = client.delete(f"/budgets/{budget_id}", headers=auth_header)
        assert resp.status_code == 200

    def test_status_endpoint(self, client, auth_header):
        resp = client.get("/budgets/status", headers=auth_header)
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_forecast_endpoint(self, client, auth_header):
        resp = client.get("/budgets/forecast", headers=auth_header)
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_generate_alerts_endpoint(self, client, auth_header):
        resp = client.post("/budgets/alerts/generate", headers=auth_header)
        assert resp.status_code == 200
        assert "new_alerts" in resp.get_json()

    def test_list_alerts_endpoint(self, client, auth_header):
        resp = client.get("/budgets/alerts", headers=auth_header)
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_mark_alert_read_not_found(self, client, auth_header):
        resp = client.patch(
            "/budgets/alerts/999/read", headers=auth_header
        )
        assert resp.status_code == 404

    def test_mark_all_read_endpoint(self, client, auth_header):
        resp = client.post("/budgets/alerts/read-all", headers=auth_header)
        assert resp.status_code == 200
        assert "marked_read" in resp.get_json()

    def test_unauthorized(self, client):
        resp = client.get("/budgets")
        assert resp.status_code == 401

    def test_full_workflow(self, client, auth_header):
        """Test complete budget → spend → alert workflow."""
        cat_id = self._create_cat_via_api(client, auth_header)

        # Create budget
        resp = client.post("/budgets", json={
            "category_id": cat_id,
            "monthly_limit": 1000,
        }, headers=auth_header)
        assert resp.status_code == 201

        # Add expenses that exceed warning
        for _ in range(9):
            client.post("/expenses", json={
                "amount": 100,
                "description": "food item",
                "category_id": cat_id,
            }, headers=auth_header)

        # Check status
        resp = client.get("/budgets/status", headers=auth_header)
        assert resp.status_code == 200
        statuses = resp.get_json()
        assert len(statuses) >= 1

        # Generate alerts
        resp = client.post("/budgets/alerts/generate", headers=auth_header)
        assert resp.status_code == 200

        # Check forecast
        resp = client.get("/budgets/forecast", headers=auth_header)
        assert resp.status_code == 200
