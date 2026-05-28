"""Tests for Dynamic Budget Suggestions."""

import pytest


class TestDynamicBudget:
    def _make_txs(self, categories_amounts):
        txs = []
        for i, (cat, amt) in enumerate(categories_amounts):
            txs.append({"id": str(i), "amount": -amt, "category": cat,
                       "date": f"2024-01-{i+1:02d}", "type": "expense"})
        return txs

    def test_basic_suggestions(self):
        from app.services.dynamic_budget import DynamicBudgetService
        svc = DynamicBudgetService()
        txs = self._make_txs([
            ("food", 800), ("housing", 1500), ("entertainment", 400),
            ("transport", 300), ("shopping", 500),
        ])
        result = svc.generate_suggestions(txs, monthly_income=5000)
        assert "suggestions" in result
        assert result["total_savings_potential"] > 0

    def test_no_overspending(self):
        from app.services.dynamic_budget import DynamicBudgetService
        svc = DynamicBudgetService()
        txs = self._make_txs([("food", 200), ("transport", 100)])
        result = svc.generate_suggestions(txs, monthly_income=5000)
        assert len(result["overspending_categories"]) == 0

    def test_savings_opportunities(self):
        from app.services.dynamic_budget import DynamicBudgetService
        svc = DynamicBudgetService()
        txs = self._make_txs([("entertainment", 1500), ("food", 500)])
        result = svc.generate_suggestions(txs, monthly_income=3000)
        opps = result["savings_opportunities"]
        assert len(opps) > 0

    def test_aggressive_mode(self):
        from app.services.dynamic_budget import DynamicBudgetService
        svc = DynamicBudgetService()
        txs = self._make_txs([("food", 800), ("entertainment", 600)])
        result_normal = svc.generate_suggestions(txs, monthly_income=5000, aggressive=False)
        result_aggressive = svc.generate_suggestions(txs, monthly_income=5000, aggressive=True)
        # Aggressive should save more
        assert result_aggressive["total_savings_potential"] >= result_normal["total_savings_potential"]
