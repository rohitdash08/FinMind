"""Tests for essential vs discretionary spending breakdown."""

import pytest
from decimal import Decimal
from app.services.spending_breakdown import (
    classify_category,
    analyze_spending_breakdown,
    get_monthly_trend,
    SpendingType,
)


class TestClassifyCategory:
    def test_essential(self):
        assert classify_category("Groceries") == SpendingType.ESSENTIAL
        assert classify_category("Rent") == SpendingType.ESSENTIAL
        assert classify_category("Health Insurance") == SpendingType.ESSENTIAL

    def test_discretionary(self):
        assert classify_category("Dining Out") == SpendingType.DISCRETIONARY
        assert classify_category("Netflix Streaming") == SpendingType.DISCRETIONARY
        assert classify_category("Shopping") == SpendingType.DISCRETIONARY

    def test_savings(self):
        assert classify_category("Emergency Savings") == SpendingType.SAVINGS
        assert classify_category("Investment") == SpendingType.SAVINGS

    def test_unclassified(self):
        assert classify_category("Miscellaneous") == SpendingType.UNCLASSIFIED

    def test_custom_rules(self):
        rules = {"coffee": SpendingType.ESSENTIAL.value}
        assert classify_category("Coffee", custom_rules=rules) == SpendingType.ESSENTIAL


class TestAnalyzeBreakdown:
    @pytest.fixture
    def sample_expenses(self):
        return [
            {"amount": 1500, "category_name": "Rent", "spent_at": "2026-02-01"},
            {"amount": 200, "category_name": "Groceries", "spent_at": "2026-02-05"},
            {"amount": 100, "category_name": "Utilities", "spent_at": "2026-02-10"},
            {"amount": 80, "category_name": "Dining Out", "spent_at": "2026-02-12"},
            {"amount": 50, "category_name": "Entertainment", "spent_at": "2026-02-15"},
            {"amount": 500, "category_name": "Savings", "spent_at": "2026-02-01"},
        ]

    def test_breakdown_totals(self, sample_expenses):
        result = analyze_spending_breakdown(sample_expenses)
        assert result["total_spending"] == 2430.0
        assert result["breakdown"]["essential"]["amount"] == 1800.0
        assert result["breakdown"]["discretionary"]["amount"] == 130.0
        assert result["breakdown"]["savings"]["amount"] == 500.0

    def test_percentages(self, sample_expenses):
        result = analyze_spending_breakdown(sample_expenses)
        assert result["breakdown"]["essential"]["percentage"] > 70

    def test_categories_sorted(self, sample_expenses):
        result = analyze_spending_breakdown(sample_expenses)
        amounts = [c["amount"] for c in result["categories"]]
        assert amounts == sorted(amounts, reverse=True)

    def test_50_30_20_rule(self, sample_expenses):
        result = analyze_spending_breakdown(sample_expenses)
        rule = result["rule_50_30_20"]
        assert "essential" in rule
        assert "discretionary" in rule
        assert "savings" in rule
        assert rule["essential"]["target"] == 50

    def test_recommendations(self, sample_expenses):
        result = analyze_spending_breakdown(sample_expenses)
        assert isinstance(result["recommendations"], list)
        assert len(result["recommendations"]) > 0

    def test_empty_expenses(self):
        result = analyze_spending_breakdown([])
        assert result["total_spending"] == 1.0  # avoid division by zero

    def test_custom_rules(self):
        expenses = [{"amount": 50, "category_name": "Coffee", "spent_at": "2026-02-01"}]
        rules = {"coffee": "essential"}
        result = analyze_spending_breakdown(expenses, custom_rules=rules)
        assert result["breakdown"]["essential"]["amount"] == 50.0


class TestMonthlyTrend:
    def test_trend(self):
        expenses = [
            {"amount": 100, "category_name": "Rent", "spent_at": "2026-01-15"},
            {"amount": 50, "category_name": "Dining", "spent_at": "2026-01-20"},
            {"amount": 120, "category_name": "Rent", "spent_at": "2026-02-15"},
            {"amount": 30, "category_name": "Shopping", "spent_at": "2026-02-20"},
        ]
        trend = get_monthly_trend(expenses, months=6)
        assert len(trend) >= 1
        assert "month" in trend[0]
        assert "essential" in trend[0]
        assert "discretionary" in trend[0]


class TestSpendingAPI:
    def test_breakdown(self, client):
        resp = client.post("/spending/breakdown", json={
            "expenses": [
                {"amount": 100, "category_name": "Groceries", "spent_at": "2026-02-01"},
                {"amount": 50, "category_name": "Dining", "spent_at": "2026-02-05"},
            ]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "breakdown" in data
        assert "recommendations" in data

    def test_breakdown_empty(self, client):
        resp = client.post("/spending/breakdown", json={"expenses": []})
        assert resp.status_code == 400

    def test_classify(self, client):
        resp = client.post("/spending/classify", json={"category_name": "Groceries"})
        assert resp.status_code == 200
        assert resp.get_json()["type"] == "essential"

    def test_classify_missing(self, client):
        resp = client.post("/spending/classify", json={})
        assert resp.status_code == 400

    def test_trend(self, client):
        resp = client.post("/spending/trend", json={
            "expenses": [
                {"amount": 100, "category_name": "Rent", "spent_at": "2026-02-01"},
            ]
        })
        assert resp.status_code == 200
