"""Loan Calculator & Amortization Schedule.

Features:
- Monthly payment calculation
- Full amortization schedule
- Extra payment scenarios
- Refinance comparison
- Loan comparison tool
- Debt-to-income ratio calculator
- Payoff date estimator
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.loan")


class LoanCalculatorService:

    def calculate_monthly_payment(self, principal: float, annual_rate: float,
                                    term_months: int) -> dict:
        """Calculate monthly loan payment."""
        if annual_rate == 0:
            payment = principal / max(term_months, 1)
        else:
            monthly_rate = annual_rate / 100 / 12
            payment = principal * (
                monthly_rate * (1 + monthly_rate) ** term_months /
                ((1 + monthly_rate) ** term_months - 1)
            )

        total_paid = payment * term_months
        total_interest = total_paid - principal

        return {
            "principal": round(principal, 2),
            "annual_rate": round(annual_rate, 4),
            "term_months": term_months,
            "monthly_payment": round(payment, 2),
            "total_paid": round(total_paid, 2),
            "total_interest": round(total_interest, 2),
            "interest_to_principal_ratio": round(
                total_interest / max(principal, 1), 4
            ),
        }

    def generate_amortization(self, principal: float, annual_rate: float,
                                term_months: int,
                                extra_payment: float = 0) -> dict:
        """Generate full amortization schedule."""
        monthly_rate = annual_rate / 100 / 12
        if annual_rate == 0:
            base_payment = principal / max(term_months, 1)
        else:
            base_payment = principal * (
                monthly_rate * (1 + monthly_rate) ** term_months /
                ((1 + monthly_rate) ** term_months - 1)
            )

        balance = principal
        schedule = []
        total_interest = 0
        month = 0
        start_date = datetime.utcnow()

        while balance > 0 and month < term_months * 2:  # safety limit
            month += 1
            interest = balance * monthly_rate
            payment = min(base_payment + extra_payment, balance + interest)
            principal_paid = payment - interest
            balance = max(balance - principal_paid, 0)
            total_interest += interest

            payment_date = (start_date + timedelta(days=30 * month)).isoformat()[:10]

            schedule.append({
                "month": month,
                "date": payment_date,
                "payment": round(payment, 2),
                "principal": round(principal_paid, 2),
                "interest": round(interest, 2),
                "extra": round(min(extra_payment, max(balance - principal_paid, 0)), 2),
                "balance": round(balance, 2),
            })

            if balance <= 0:
                break

        actual_months = month
        actual_total = sum(s["payment"] for s in schedule)

        return {
            "original_term_months": term_months,
            "actual_term_months": actual_months,
            "months_saved": term_months - actual_months if extra_payment > 0 else 0,
            "monthly_payment": round(base_payment, 2),
            "extra_payment": round(extra_payment, 2),
            "total_paid": round(actual_total, 2),
            "total_interest": round(total_interest, 2),
            "interest_saved": round(
                base_payment * term_months - principal - total_interest, 2
            ),
            "schedule": schedule,
        }

    def compare_refinance(self, current_balance: float,
                           current_rate: float, current_remaining_months: int,
                           new_rate: float, new_term_months: int,
                           closing_costs: float = 0) -> dict:
        """Compare current loan vs refinance."""
        current_calc = self.calculate_monthly_payment(
            current_balance, current_rate, current_remaining_months
        )
        new_calc = self.calculate_monthly_payment(
            current_balance, new_rate, new_term_months
        )

        current_total = current_calc["total_paid"]
        new_total = new_calc["total_paid"] + closing_costs

        monthly_savings = current_calc["monthly_payment"] - new_calc["monthly_payment"]
        total_savings = current_total - new_total
        breakeven_months = closing_costs / max(monthly_savings, 0.01)

        return {
            "current_loan": {
                "balance": round(current_balance, 2),
                "rate": round(current_rate, 4),
                "remaining_months": current_remaining_months,
                "monthly_payment": current_calc["monthly_payment"],
                "total_remaining": round(current_total, 2),
            },
            "refinance": {
                "new_rate": round(new_rate, 4),
                "new_term": new_term_months,
                "monthly_payment": new_calc["monthly_payment"],
                "total_cost": round(new_total, 2),
                "closing_costs": round(closing_costs, 2),
            },
            "monthly_savings": round(monthly_savings, 2),
            "total_savings": round(total_savings, 2),
            "breakeven_months": round(breakeven_months, 1),
            "recommendation": "refinance" if total_savings > 0 else "keep_current",
        }

    def compare_loans(self, loans: list[dict]) -> dict:
        """Compare multiple loan options."""
        results = []
        for i, loan in enumerate(loans):
            calc = self.calculate_monthly_payment(
                float(loan.get("principal", 0)),
                float(loan.get("rate", 0)),
                int(loan.get("term_months", 0)),
            )
            calc["name"] = loan.get("name", f"Loan {i+1}")
            calc["lender"] = loan.get("lender", "")
            results.append(calc)

        best = min(results, key=lambda x: x["total_paid"])
        return {
            "loans": results,
            "best_option": best["name"],
            "total_savings_vs_worst": round(
                max(r["total_paid"] for r in results) - best["total_paid"], 2
            ),
        }

    def debt_to_income(self, monthly_debt: float, monthly_income: float) -> dict:
        """Calculate debt-to-income ratio."""
        ratio = monthly_debt / max(monthly_income, 1) * 100

        if ratio <= 20:
            status = "excellent"
        elif ratio <= 36:
            status = "good"
        elif ratio <= 43:
            status = "fair"
        else:
            status = "poor"

        return {
            "monthly_income": round(monthly_income, 2),
            "monthly_debt": round(monthly_debt, 2),
            "dti_ratio": round(ratio, 1),
            "status": status,
            "max_mortgage_payment": round(monthly_income * 0.28, 2),
            "max_total_debt_payment": round(monthly_income * 0.36, 2),
        }

    def payoff_date(self, balance: float, rate: float,
                     monthly_payment: float) -> dict:
        """Calculate payoff date for a debt."""
        monthly_rate = rate / 100 / 12

        if monthly_payment <= balance * monthly_rate:
            return {"error": "Payment too low - debt will never be paid off"}

        month = 0
        total_interest = 0
        remaining = balance

        while remaining > 0 and month < 600:  # 50 year max
            month += 1
            interest = remaining * monthly_rate
            principal_paid = min(monthly_payment - interest, remaining)
            remaining -= principal_paid
            total_interest += interest
            if remaining <= 0:
                break

        payoff_date = (datetime.utcnow() + timedelta(days=30 * month)).isoformat()[:10]

        return {
            "balance": round(balance, 2),
            "monthly_payment": round(monthly_payment, 2),
            "months_to_payoff": month,
            "years_to_payoff": round(month / 12, 1),
            "payoff_date": payoff_date,
            "total_paid": round(balance + total_interest, 2),
            "total_interest": round(total_interest, 2),
        }
