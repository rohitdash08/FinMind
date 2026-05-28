"""Tax Calculator & Estimator.

Tax calculation features:
- Federal tax brackets (US 2024)
- Standard deduction vs itemized
- Capital gains estimation
- Tax-advantaged account contribution limits
- Quarterly estimated tax calculator
- Tax withholding calculator
- Deduction finder
- Tax bracket projection
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("finmind.tax")


class FilingStatus(str, Enum):
    SINGLE = "single"
    MARRIED_JOINT = "married_joint"
    MARRIED_SEPARATE = "married_separate"
    HEAD_OF_HOUSEHOLD = "head_of_household"


# 2024 US Federal Tax Brackets
TAX_BRACKETS = {
    FilingStatus.SINGLE: [
        (11600, 0.10),
        (47150, 0.12),
        (100525, 0.22),
        (191950, 0.24),
        (243725, 0.32),
        (609350, 0.35),
        (float("inf"), 0.37),
    ],
    FilingStatus.MARRIED_JOINT: [
        (23200, 0.10),
        (94300, 0.12),
        (201050, 0.22),
        (383900, 0.24),
        (487450, 0.32),
        (731200, 0.35),
        (float("inf"), 0.37),
    ],
    FilingStatus.MARRIED_SEPARATE: [
        (11600, 0.10),
        (47150, 0.12),
        (100525, 0.22),
        (191950, 0.24),
        (243725, 0.32),
        (365600, 0.35),
        (float("inf"), 0.37),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (16550, 0.10),
        (63100, 0.12),
        (100500, 0.22),
        (191950, 0.24),
        (243700, 0.32),
        (609350, 0.35),
        (float("inf"), 0.37),
    ],
}

STANDARD_DEDUCTION = {
    FilingStatus.SINGLE: 14600,
    FilingStatus.MARRIED_JOINT: 29200,
    FilingStatus.MARRIED_SEPARATE: 14600,
    FilingStatus.HEAD_OF_HOUSEHOLD: 21900,
}

# Long-term capital gains rates
CAPITAL_GAINS_BRACKETS = [
    (44625, 0.0),
    (496300, 0.15),
    (float("inf"), 0.20),
]


@dataclass
class TaxResult:
    gross_income: float
    total_deductions: float
    taxable_income: float
    federal_tax: float
    effective_rate: float
    marginal_rate: float
    bracket_breakdown: list = field(default_factory=list)

    def to_dict(self):
        return {
            "gross_income": round(self.gross_income, 2),
            "total_deductions": round(self.total_deductions, 2),
            "taxable_income": round(self.taxable_income, 2),
            "federal_tax": round(self.federal_tax, 2),
            "effective_rate": round(self.effective_rate, 2),
            "marginal_rate": round(self.marginal_rate, 2),
            "bracket_breakdown": self.bracket_breakdown,
        }


class TaxCalculatorService:
    """Tax calculation and estimation."""

    def __init__(self):
        self.user_data = {}  # user_id -> tax data

    def calculate_federal_tax(self, gross_income: float,
                                filing_status: str = "single",
                                deductions: list = None,
                                credits: list = None,
                                withholdings: float = 0) -> dict:
        """Calculate federal income tax."""
        status = FilingStatus(filing_status)

        # Calculate deductions
        itemized = sum(deductions or [])
        standard = STANDARD_DEDUCTION[status]
        total_deductions = max(itemized, standard)

        taxable = max(gross_income - total_deductions, 0)

        # Calculate tax by bracket
        brackets = TAX_BRACKETS[status]
        tax = 0
        remaining = taxable
        breakdown = []
        marginal_rate = 0

        prev_limit = 0
        for limit, rate in brackets:
            bracket_income = min(remaining, limit - prev_limit)
            bracket_tax = bracket_income * rate

            if bracket_income > 0:
                breakdown.append({
                    "range": f"${prev_limit:,} - ${min(limit, taxable + total_deductions):,}",
                    "rate": f"{rate * 100:.0f}%",
                    "income_in_bracket": round(bracket_income, 2),
                    "tax": round(bracket_tax, 2),
                })
                tax += bracket_tax
                remaining -= bracket_income
                marginal_rate = rate * 100

            prev_limit = limit
            if remaining <= 0:
                break

        # Apply credits
        total_credits = sum(credits or [])
        tax = max(tax - total_credits, 0)

        effective_rate = (tax / max(gross_income, 1)) * 100

        result = TaxResult(
            gross_income=gross_income,
            total_deductions=total_deductions,
            taxable_income=taxable,
            federal_tax=tax,
            effective_rate=effective_rate,
            marginal_rate=marginal_rate,
            bracket_breakdown=breakdown,
        )

        refund_or_owed = withholdings - tax

        return {
            **result.to_dict(),
            "filing_status": filing_status,
            "deduction_type": "itemized" if itemized > standard else "standard",
            "credits_applied": round(total_credits, 2),
            "withholdings": round(withholdings, 2),
            "refund": round(max(refund_or_owed, 0), 2),
            "amount_owed": round(max(-refund_or_owed, 0), 2),
        }

    def estimate_quarterly_tax(self, annual_income: float,
                                 filing_status: str = "single",
                                 deductions: list = None) -> dict:
        """Estimate quarterly tax payments."""
        calc = self.calculate_federal_tax(annual_income, filing_status, deductions)

        quarterly = round(calc["federal_tax"] / 4, 2)

        return {
            "annual_income": round(annual_income, 2),
            "estimated_annual_tax": calc["federal_tax"],
            "quarterly_payment": quarterly,
            "effective_rate": calc["effective_rate"],
            "payment_schedule": [
                {"quarter": "Q1 (Apr 15)", "amount": quarterly},
                {"quarter": "Q2 (Jun 15)", "amount": quarterly},
                {"quarter": "Q3 (Sep 15)", "amount": quarterly},
                {"quarter": "Q4 (Jan 15)", "amount": quarterly},
            ],
        }

    def calculate_capital_gains(self, short_term_gains: float,
                                  long_term_gains: float,
                                  ordinary_income: float = 0,
                                  filing_status: str = "single") -> dict:
        """Calculate capital gains tax."""
        # Short-term gains taxed as ordinary income
        total_ordinary = ordinary_income + short_term_gains
        st_tax_calc = self.calculate_federal_tax(total_ordinary, filing_status)
        ordinary_tax = st_tax_calc["federal_tax"]

        # Long-term gains with preferential rates
        lt_tax = 0
        remaining_lt = long_term_gains
        prev = 0
        for limit, rate in CAPITAL_GAINS_BRACKETS:
            bracket = min(remaining_lt, max(limit - prev, 0))
            lt_tax += bracket * rate
            remaining_lt -= bracket
            prev = limit
            if remaining_lt <= 0:
                break

        total_tax = ordinary_tax + lt_tax
        total_gains = short_term_gains + long_term_gains

        return {
            "short_term_gains": round(short_term_gains, 2),
            "long_term_gains": round(long_term_gains, 2),
            "total_gains": round(total_gains, 2),
            "short_term_tax": round(ordinary_tax, 2),
            "long_term_tax": round(lt_tax, 2),
            "total_tax": round(total_tax, 2),
            "effective_rate": round(total_tax / max(total_gains, 1) * 100, 2),
        }

    def suggest_deductions(self, expenses: dict) -> list[dict]:
        """Suggest potential tax deductions."""
        suggestions = []

        deduction_map = {
            "mortgage_interest": {"limit": 750000, "category": "Itemized", "desc": "Mortgage interest deduction"},
            "charitable_donations": {"limit": 0.6, "category": "Itemized", "desc": "Charitable contributions (up to 60% AGI)"},
            "medical_expenses": {"limit": 0.075, "category": "Itemized", "desc": "Medical expenses exceeding 7.5% AGI"},
            "state_local_taxes": {"limit": 10000, "category": "SALT", "desc": "State/local taxes (SALT, $10k cap)"},
            "home_office": {"limit": 1500, "category": "Business", "desc": "Home office deduction (simplified $5/sq ft)"},
            "student_loan_interest": {"limit": 2500, "category": "Adjustment", "desc": "Student loan interest (up to $2,500)"},
            "ira_contribution": {"limit": 7000, "category": "Retirement", "desc": "Traditional IRA contribution (up to $7,000)"},
            "self_employment": {"limit": 0, "category": "Business", "desc": "Self-employment tax deduction (50%)"},
            "health_savings": {"limit": 4150, "category": "Health", "desc": "HSA contribution (up to $4,150 individual)"},
        }

        for expense_key, amount in expenses.items():
            if expense_key in deduction_map and amount > 0:
                info = deduction_map[expense_key]
                suggestions.append({
                    "type": expense_key,
                    "amount": round(amount, 2),
                    "category": info["category"],
                    "description": info["desc"],
                    "annual_limit": info["limit"],
                })

        return sorted(suggestions, key=lambda x: x["amount"], reverse=True)

    def calculate_paycheck_withholding(self, annual_salary: float,
                                         pay_frequency: str = "biweekly",
                                         filing_status: str = "single",
                                         allowances: int = 0) -> dict:
        """Calculate recommended paycheck withholding."""
        tax_calc = self.calculate_federal_tax(annual_salary, filing_status)

        periods = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12}
        num_periods = periods.get(pay_frequency, 26)

        per_paycheck = round(tax_calc["federal_tax"] / num_periods, 2)
        gross_per_paycheck = round(annual_salary / num_periods, 2)

        return {
            "annual_salary": round(annual_salary, 2),
            "annual_tax": tax_calc["federal_tax"],
            "effective_rate": tax_calc["effective_rate"],
            "gross_per_paycheck": gross_per_paycheck,
            "federal_withholding_per_paycheck": per_paycheck,
            "net_per_paycheck_est": round(gross_per_paycheck - per_paycheck, 2),
            "pay_frequency": pay_frequency,
            "filing_status": filing_status,
        }
