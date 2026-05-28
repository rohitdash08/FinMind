"""Tests for Tax Calculator."""

import pytest


class TestTaxCalculator:
    def test_basic_tax_single(self):
        from app.services.tax_calculator import TaxCalculatorService
        svc = TaxCalculatorService()
        result = svc.calculate_federal_tax(80000, "single")
        assert result["gross_income"] == 80000
        assert result["federal_tax"] > 0
        assert result["effective_rate"] > 0
        assert result["marginal_rate"] == 22.0

    def test_standard_deduction(self):
        from app.services.tax_calculator import TaxCalculatorService
        svc = TaxCalculatorService()
        result = svc.calculate_federal_tax(50000, "single")
        assert result["taxable_income"] == 50000 - 14600

    def test_zero_income(self):
        from app.services.tax_calculator import TaxCalculatorService
        svc = TaxCalculatorService()
        result = svc.calculate_federal_tax(0)
        assert result["federal_tax"] == 0
        assert result["refund"] == 0

    def test_refund_calculation(self):
        from app.services.tax_calculator import TaxCalculatorService
        svc = TaxCalculatorService()
        result = svc.calculate_federal_tax(60000, withholdings=10000)
        assert result["refund"] > 0

    def test_quarterly_estimate(self):
        from app.services.tax_calculator import TaxCalculatorService
        svc = TaxCalculatorService()
        result = svc.estimate_quarterly_tax(100000)
        assert result["quarterly_payment"] > 0
        assert len(result["payment_schedule"]) == 4

    def test_capital_gains(self):
        from app.services.tax_calculator import TaxCalculatorService
        svc = TaxCalculatorService()
        result = svc.calculate_capital_gains(5000, 10000)
        assert result["short_term_gains"] == 5000
        assert result["long_term_gains"] == 10000
        assert result["total_tax"] > 0

    def test_deduction_suggestions(self):
        from app.services.tax_calculator import TaxCalculatorService
        svc = TaxCalculatorService()
        result = svc.suggest_deductions({
            "mortgage_interest": 12000,
            "charitable_donations": 5000,
            "student_loan_interest": 2000,
        })
        assert len(result) == 3
        assert result[0]["amount"] == 12000

    def test_withholding(self):
        from app.services.tax_calculator import TaxCalculatorService
        svc = TaxCalculatorService()
        result = svc.calculate_paycheck_withholding(80000)
        assert result["federal_withholding_per_paycheck"] > 0
        assert result["pay_frequency"] == "biweekly"
