"""Tests for comparative spending analysis."""

import pytest


class TestCategoryComparison:
    def test_basic_comparison(self):
        from app.services.comparative import compare_categories
        txs = [
            {"category": "food", "amount": 50},
            {"category": "food", "amount": 30},
            {"category": "transport", "amount": 20},
        ]
        result = compare_categories(txs)
        assert result["total_categories"] == 2
        assert result["categories"][0]["category"] == "food"

    def test_pairwise_comparisons(self):
        from app.services.comparative import compare_categories
        txs = [{"category": c, "amount": a} for c, a in [
            ("food", 100), ("transport", 50), ("entertainment", 30)
        ]]
        result = compare_categories(txs)
        assert len(result["pairwise_comparisons"]) >= 1

    def test_empty(self):
        from app.services.comparative import compare_categories
        result = compare_categories([])
        assert result["total_categories"] == 0


class TestPeriodComparison:
    def test_basic_period(self):
        from app.services.comparative import compare_periods
        curr = [{"category": "food", "amount": 100, "merchant": "A"}]
        prev = [{"category": "food", "amount": 80, "merchant": "A"}]
        result = compare_periods(curr, prev, "June", "May")
        assert result["total"]["difference"] == 20.0

    def test_new_category(self):
        from app.services.comparative import compare_periods
        curr = [{"category": "food", "amount": 50}, {"category": "gaming", "amount": 100}]
        prev = [{"category": "food", "amount": 50}]
        result = compare_periods(curr, prev)
        statuses = [c["status"] for c in result["category_changes"]]
        assert "new" in statuses


class TestIncomeExpenses:
    def test_savings(self):
        from app.services.comparative import compare_income_expenses
        txs = [{"category": "food", "amount": 300}, {"category": "rent", "amount": 500}]
        result = compare_income_expenses(1000, txs)
        assert result["savings"] == 200.0
        assert result["savings_rate"] == 20.0
        assert result["assessment"] == "excellent"

    def test_overspending(self):
        from app.services.comparative import compare_income_expenses
        txs = [{"category": "food", "amount": 1500}]
        result = compare_income_expenses(1000, txs)
        assert result["assessment"] == "overspending"
