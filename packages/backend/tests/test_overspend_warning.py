"""Tests for category overspend early warning system."""

import pytest
from datetime import date
from app.services.overspend_warning import (
    check_overspend,
    _classify_alert,
    AlertLevel,
)


class TestClassifyAlert:
    def test_safe(self):
        assert _classify_alert(50) == AlertLevel.SAFE

    def test_caution(self):
        assert _classify_alert(75) == AlertLevel.CAUTION

    def test_warning(self):
        assert _classify_alert(90) == AlertLevel.WARNING

    def test_exceeded(self):
        assert _classify_alert(110) == AlertLevel.EXCEEDED


class TestCheckOverspend:
    def test_within_budget(self):
        expenses = [
            {"amount": 50, "category_name": "dining", "spent_at": "2026-02-10"},
            {"amount": 30, "category_name": "dining", "spent_at": "2026-02-15"},
        ]
        budgets = {"dining": 200}
        result = check_overspend(expenses, budgets, "2026-02-01", "2026-02-28")
        assert result["alerts"][0]["level"] == AlertLevel.SAFE
        assert result["alerts"][0]["spent"] == 80

    def test_exceeded_budget(self):
        expenses = [
            {"amount": 150, "category_name": "dining", "spent_at": "2026-02-05"},
            {"amount": 100, "category_name": "dining", "spent_at": "2026-02-10"},
        ]
        budgets = {"dining": 200}
        result = check_overspend(expenses, budgets, "2026-02-01", "2026-02-28")
        assert result["alerts"][0]["level"] == AlertLevel.EXCEEDED
        assert result["alerts"][0]["pct_used"] > 100

    def test_warning_level(self):
        expenses = [
            {"amount": 180, "category_name": "groceries", "spent_at": "2026-02-15"},
        ]
        budgets = {"groceries": 200}
        result = check_overspend(expenses, budgets, "2026-02-01", "2026-02-28")
        assert result["alerts"][0]["level"] == AlertLevel.WARNING

    def test_multiple_categories(self):
        expenses = [
            {"amount": 50, "category_name": "dining", "spent_at": "2026-02-10"},
            {"amount": 300, "category_name": "groceries", "spent_at": "2026-02-10"},
        ]
        budgets = {"dining": 200, "groceries": 250}
        result = check_overspend(expenses, budgets, "2026-02-01", "2026-02-28")
        assert result["summary"]["exceeded_count"] == 1
        assert result["summary"]["categories_tracked"] == 2

    def test_unbudgeted_spending(self):
        expenses = [
            {"amount": 50, "category_name": "dining", "spent_at": "2026-02-10"},
            {"amount": 100, "category_name": "shopping", "spent_at": "2026-02-10"},
        ]
        budgets = {"dining": 200}
        result = check_overspend(expenses, budgets, "2026-02-01", "2026-02-28")
        assert "shopping" in result["unbudgeted_spending"]

    def test_projected_spending(self):
        expenses = [
            {"amount": 100, "category_name": "dining", "spent_at": "2026-02-05"},
        ]
        budgets = {"dining": 200}
        result = check_overspend(expenses, budgets, "2026-02-01", "2026-02-10")
        assert result["alerts"][0]["projected_total"] > 100

    def test_action_needed(self):
        expenses = [
            {"amount": 190, "category_name": "dining", "spent_at": "2026-02-15"},
        ]
        budgets = {"dining": 200}
        result = check_overspend(expenses, budgets, "2026-02-01", "2026-02-28")
        assert result["alerts"][0]["action_needed"] is True

    def test_recommendations(self):
        expenses = [
            {"amount": 250, "category_name": "dining", "spent_at": "2026-02-15"},
        ]
        budgets = {"dining": 200}
        result = check_overspend(expenses, budgets, "2026-02-01", "2026-02-28")
        assert len(result["recommendations"]) >= 1

    def test_empty_expenses(self):
        result = check_overspend([], {"dining": 200}, "2026-02-01", "2026-02-28")
        assert result["alerts"][0]["spent"] == 0
        assert result["alerts"][0]["level"] == AlertLevel.SAFE

    def test_sorted_by_severity(self):
        expenses = [
            {"amount": 250, "category_name": "dining", "spent_at": "2026-02-10"},
            {"amount": 50, "category_name": "groceries", "spent_at": "2026-02-10"},
        ]
        budgets = {"dining": 200, "groceries": 400}
        result = check_overspend(expenses, budgets, "2026-02-01", "2026-02-28")
        assert result["alerts"][0]["level"] == AlertLevel.EXCEEDED


class TestOverspendAPI:
    def test_check(self, client):
        resp = client.post("/overspend/check", json={
            "expenses": [{"amount": 150, "category_name": "dining", "spent_at": "2026-02-10"}],
            "budgets": {"dining": 200},
            "period_start": "2026-02-01",
            "period_end": "2026-02-28",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "alerts" in data
        assert "summary" in data

    def test_missing_budgets(self, client):
        resp = client.post("/overspend/check", json={"expenses": []})
        assert resp.status_code == 400
