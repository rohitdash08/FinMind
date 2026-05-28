"""Tests for Loan Calculator."""

import pytest


class TestLoanCalculator:
    def test_monthly_payment(self):
        from app.services.loan_calculator import LoanCalculatorService
        svc = LoanCalculatorService()
        result = svc.calculate_monthly_payment(300000, 6.5, 360)
        assert result["monthly_payment"] > 0
        assert result["total_interest"] > 0

    def test_amortization(self):
        from app.services.loan_calculator import LoanCalculatorService
        svc = LoanCalculatorService()
        result = svc.generate_amortization(100000, 5.0, 120)
        assert len(result["schedule"]) == 120
        assert result["schedule"][-1]["balance"] == 0

    def test_amortization_with_extra(self):
        from app.services.loan_calculator import LoanCalculatorService
        svc = LoanCalculatorService()
        normal = svc.generate_amortization(100000, 5.0, 120)
        extra = svc.generate_amortization(100000, 5.0, 120, extra_payment=200)
        assert extra["months_saved"] > 0

    def test_refinance(self):
        from app.services.loan_calculator import LoanCalculatorService
        svc = LoanCalculatorService()
        result = svc.compare_refinance(250000, 6.5, 300, 5.0, 240)
        assert "recommendation" in result
        assert result["monthly_savings"] > 0

    def test_dti(self):
        from app.services.loan_calculator import LoanCalculatorService
        svc = LoanCalculatorService()
        result = svc.debt_to_income(1500, 5000)
        assert result["dti_ratio"] == 30.0
        assert result["status"] == "good"

    def test_payoff_date(self):
        from app.services.loan_calculator import LoanCalculatorService
        svc = LoanCalculatorService()
        result = svc.payoff_date(10000, 18.0, 500)
        assert result["months_to_payoff"] > 0

    def test_zero_interest(self):
        from app.services.loan_calculator import LoanCalculatorService
        svc = LoanCalculatorService()
        result = svc.calculate_monthly_payment(12000, 0, 12)
        assert result["monthly_payment"] == 1000
