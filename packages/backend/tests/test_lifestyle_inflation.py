"""Tests for lifestyle inflation detection."""

import pytest
from datetime import date, timedelta
from app.services.lifestyle_inflation import (
    detect_lifestyle_inflation,
    _classify_severity,
    _group_by_month,
    InflationSeverity,
)


def _make_expenses(monthly_amounts: list, category: str = "general") -> list:
    """Helper: create expenses spread across months."""
    today = date.today()
    expenses = []
    for i, amount in enumerate(monthly_amounts):
        d = today - timedelta(days=30 * (len(monthly_amounts) - 1 - i))
        expenses.append({
            "amount": amount,
            "category_name": category,
            "spent_at": str(d),
        })
    return expenses


class TestClassifySeverity:
    def test_none(self):
        assert _classify_severity(3) == InflationSeverity.NONE

    def test_mild(self):
        assert _classify_severity(10) == InflationSeverity.MILD

    def test_moderate(self):
        assert _classify_severity(20) == InflationSeverity.MODERATE

    def test_severe(self):
        assert _classify_severity(40) == InflationSeverity.SEVERE


class TestGroupByMonth:
    def test_groups_correctly(self):
        today = date.today()
        expenses = [
            {"amount": 10, "spent_at": str(today)},
            {"amount": 20, "spent_at": str(today - timedelta(days=35))},
        ]
        groups = _group_by_month(expenses, months=3)
        assert len(groups) >= 1


class TestDetectInflation:
    def test_stable_spending(self):
        expenses = _make_expenses([100, 100, 100, 105, 100, 102])
        result = detect_lifestyle_inflation(expenses)
        assert result["severity"] == InflationSeverity.NONE

    def test_severe_inflation(self):
        expenses = _make_expenses([100, 110, 120, 150, 170, 200])
        result = detect_lifestyle_inflation(expenses)
        assert result["severity"] in [InflationSeverity.MODERATE, InflationSeverity.SEVERE]
        assert result["spending_growth_pct"] > 15

    def test_insufficient_data(self):
        expenses = _make_expenses([100])
        result = detect_lifestyle_inflation(expenses)
        assert result["severity"] == InflationSeverity.NONE
        assert "Not enough data" in result["message"]

    def test_with_income(self):
        expenses = _make_expenses([2000, 2000, 2000, 2500, 2800, 3000])
        result = detect_lifestyle_inflation(expenses, income_monthly=5000)
        assert "savings_impact" in result
        assert "early_savings_rate" in result["savings_impact"]
        assert "recent_savings_rate" in result["savings_impact"]

    def test_category_trends(self):
        today = date.today()
        expenses = []
        for i in range(6):
            d = today - timedelta(days=30 * (5 - i))
            base = 50 if i < 3 else 100
            expenses.append({"amount": base, "category_name": "dining", "spent_at": str(d)})
            expenses.append({"amount": 200, "category_name": "rent", "spent_at": str(d)})
        result = detect_lifestyle_inflation(expenses)
        assert len(result["category_trends"]) >= 1

    def test_recommendations(self):
        expenses = _make_expenses([100, 100, 100, 150, 180, 200])
        result = detect_lifestyle_inflation(expenses)
        assert len(result["recommendations"]) >= 1

    def test_monthly_totals(self):
        expenses = _make_expenses([100, 200, 300])
        result = detect_lifestyle_inflation(expenses)
        assert len(result["monthly_totals"]) >= 2


class TestLifestyleAPI:
    def test_inflation_check(self, client):
        today = date.today()
        expenses = []
        for i in range(6):
            d = today - timedelta(days=30 * (5 - i))
            expenses.append({"amount": 100 + i * 20, "category_name": "general", "spent_at": str(d)})
        resp = client.post("/lifestyle/inflation", json={
            "expenses": expenses,
            "income_monthly": 5000,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "severity" in data
        assert "recommendations" in data

    def test_empty_expenses(self, client):
        resp = client.post("/lifestyle/inflation", json={"expenses": []})
        assert resp.status_code == 400
