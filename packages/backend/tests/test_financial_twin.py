"""Tests for Financial Digital Twin."""

import pytest


class TestFinancialTwin:
    def test_health_score_excellent(self):
        from app.services.financial_twin import FinancialTwin
        twin = FinancialTwin(
            monthly_income=5000,
            monthly_expenses=[{"category": "rent", "amount": 1000}],
            current_savings=30000,
        )
        health = twin.health_score()
        assert health["score"] >= 60
        assert health["grade"] in "ABCD"

    def test_health_score_poor(self):
        from app.services.financial_twin import FinancialTwin
        twin = FinancialTwin(
            monthly_income=2000,
            monthly_expenses=[{"category": "rent", "amount": 1800}],
            current_savings=100,
            debts=[{"amount": 50000}],
        )
        health = twin.health_score()
        assert health["score"] < 60

    def test_simulation(self):
        from app.services.financial_twin import FinancialTwin
        twin = FinancialTwin(
            monthly_income=5000,
            monthly_expenses=[{"category": "rent", "amount": 2000}],
            current_savings=10000,
        )
        result = twin.simulate_months(6)
        assert "projections" in result
        assert result["months_simulated"] == 6

    def test_what_if_job_loss(self):
        from app.services.financial_twin import FinancialTwin
        twin = FinancialTwin(
            monthly_income=5000,
            monthly_expenses=[{"category": "rent", "amount": 2000}],
            current_savings=15000,
        )
        result = twin.what_if("job_loss")
        assert result["risk_of_negative"] > 0

    def test_recommendations(self):
        from app.services.financial_twin import FinancialTwin
        twin = FinancialTwin(
            monthly_income=3000,
            monthly_expenses=[{"category": "rent", "amount": 2800}],
            current_savings=500,
        )
        recs = twin.recommend()
        assert len(recs) >= 1
        assert recs[0]["priority"] in ("critical", "high", "medium", "low")
