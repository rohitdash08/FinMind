"""Tests for Financial Health Score."""

import pytest


class TestFinancialHealth:
    def _make_expenses(self, categories_amounts):
        return [
            {"amount": -amt, "category": cat, "type": "expense",
             "date": f"2024-01-{i+1:02d}"}
            for i, (cat, amt) in enumerate(categories_amounts)
        ]

    def test_excellent_health(self):
        from app.services.financial_health import FinancialHealthService
        svc = FinancialHealthService()
        result = svc.calculate(
            monthly_income=10000,
            monthly_expenses=self._make_expenses([
                ("housing", 2000), ("food", 500), ("transport", 300),
                ("entertainment", 200), ("utilities", 100), ("health", 100),
            ]),
            savings_balance=50000,
            investment_balance=30000,
        )
        assert result["grade"] in ("A", "B")
        assert result["percentage"] >= 70

    def test_poor_health(self):
        from app.services.financial_health import FinancialHealthService
        svc = FinancialHealthService()
        result = svc.calculate(
            monthly_income=3000,
            monthly_expenses=self._make_expenses([("housing", 3000), ("food", 500)]),
            savings_balance=0,
            debt_balance=20000,
            monthly_debt_payment=1500,
        )
        assert result["grade"] in ("D", "F")

    def test_recommendations(self):
        from app.services.financial_health import FinancialHealthService
        svc = FinancialHealthService()
        result = svc.calculate(
            monthly_income=5000,
            monthly_expenses=self._make_expenses([("food", 4000)]),
            savings_balance=0,
        )
        assert len(result["top_recommendations"]) > 0

    def test_categories_count(self):
        from app.services.financial_health import FinancialHealthService
        svc = FinancialHealthService()
        result = svc.calculate(monthly_income=5000,
                               monthly_expenses=self._make_expenses([("food", 100)]))
        assert len(result["categories"]) == 6
