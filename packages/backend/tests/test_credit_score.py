"""Tests for Credit Score Tracker."""

import pytest


class TestCreditScore:
    def test_add_score(self):
        from app.services.credit_score import CreditScoreService
        svc = CreditScoreService()
        result = svc.add_score("u1", 720)
        assert result["status"] == "recorded"
        assert result["rating"] == "very_good"

    def test_invalid_score(self):
        from app.services.credit_score import CreditScoreService
        svc = CreditScoreService()
        result = svc.add_score("u1", 900)
        assert "error" in result

    def test_history(self):
        from app.services.credit_score import CreditScoreService
        svc = CreditScoreService()
        svc.add_score("u1", 680, date="2025-01-01")
        svc.add_score("u1", 700, date="2025-02-01")
        svc.add_score("u1", 720, date="2025-03-01")
        history = svc.get_history("u1")
        assert history["change"] == 20
        assert history["change_direction"] == "up"
        assert history["highest"] == 720

    def test_simulate(self):
        from app.services.credit_score import CreditScoreService
        svc = CreditScoreService()
        result = svc.simulate("u1", 680, ["pay_all_on_time", "reduce_utilization_50"])
        assert result["simulated_score"] > 680

    def test_factor_breakdown(self):
        from app.services.credit_score import CreditScoreService
        svc = CreditScoreService()
        result = svc.get_factor_breakdown("u1", 720)
        assert len(result["factors"]) == 5

    def test_improvement_plan(self):
        from app.services.credit_score import CreditScoreService
        svc = CreditScoreService()
        result = svc.get_improvement_plan("u1", current_score=650, target_score=750)
        assert result["gap"] == 100
        assert len(result["actions"]) > 0

    def test_utilization(self):
        from app.services.credit_score import CreditScoreService
        svc = CreditScoreService()
        result = svc.calculate_utilization([3000, 2000], [10000, 5000])
        assert result["overall_utilization"] == 33.3
        assert result["status"] == "fair"
