"""Personal Financial Digital Twin Simulator.

Simulates financial outcomes based on:
- Current spending patterns
- Income projections
- Savings goals
- What-if scenarios (job loss, raise, emergency, etc.)

Generates probabilistic forecasts with confidence intervals.
"""

import logging
import random
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional

logger = logging.getLogger("finmind.twin")


class FinancialTwin:
    """Digital twin that mirrors user financial behavior and simulates futures."""

    def __init__(
        self,
        monthly_income: float,
        monthly_expenses: list[dict],
        current_savings: float = 0,
        debts: list[dict] = None,
    ):
        self.monthly_income = monthly_income
        self.expenses = monthly_expenses
        self.current_savings = current_savings
        self.debts = debts or []

        # Build profile
        self._category_totals = defaultdict(float)
        for exp in self.expenses:
            self._category_totals[exp.get("category", "other")] += float(exp.get("amount", 0))
        self.total_monthly_expenses = sum(self._category_totals.values())
        self.monthly_surplus = self.monthly_income - self.total_monthly_expenses
        self.savings_rate = (self.monthly_surplus / self.monthly_income * 100) if self.monthly_income else 0

    def health_score(self) -> dict:
        """Calculate overall financial health score (0-100)."""
        score = 50  # Base score

        # Savings rate contribution (max +25)
        if self.savings_rate >= 30:
            score += 25
        elif self.savings_rate >= 20:
            score += 20
        elif self.savings_rate >= 10:
            score += 15
        elif self.savings_rate >= 0:
            score += 5

        # Emergency fund (max +15)
        months_runway = self.current_savings / self.total_monthly_expenses if self.total_monthly_expenses else 0
        if months_runway >= 6:
            score += 15
        elif months_runway >= 3:
            score += 10
        elif months_runway >= 1:
            score += 5

        # Debt burden (max -20)
        total_debt = sum(float(d.get("amount", 0)) for d in self.debts)
        debt_to_income = total_debt / (self.monthly_income * 12) if self.monthly_income else 0
        if debt_to_income > 0.5:
            score -= 20
        elif debt_to_income > 0.3:
            score -= 10
        elif debt_to_income > 0.1:
            score -= 5

        # Expense diversification (max +10)
        n_categories = len(self._category_totals)
        if n_categories >= 5:
            score += 10
        elif n_categories >= 3:
            score += 5

        score = max(0, min(100, score))

        if score >= 80:
            grade = "A"
        elif score >= 60:
            grade = "B"
        elif score >= 40:
            grade = "C"
        else:
            grade = "D"

        return {
            "score": score,
            "grade": grade,
            "savings_rate": round(self.savings_rate, 1),
            "emergency_months": round(months_runway, 1),
            "debt_to_income": round(debt_to_income, 2),
        }

    def simulate_months(self, months: int = 12, scenarios: dict = None) -> dict:
        """Run Monte Carlo simulation for N months."""
        scenarios = scenarios or {}
        income_change = scenarios.get("income_change", 0)  # e.g., 0.1 = 10% raise
        expense_change = scenarios.get("expense_change", 0)
        one_time_event = scenarios.get("one_time_event", 0)  # e.g., -5000 emergency

        simulations = []
        for _ in range(100):  # 100 Monte Carlo runs
            savings = self.current_savings - one_time_event
            trajectory = [savings]

            for m in range(months):
                # Monthly income with noise
                monthly_inc = self.monthly_income * (1 + income_change) * random.gauss(1.0, 0.05)
                # Monthly expenses with noise
                monthly_exp = self.total_monthly_expenses * (1 + expense_change) * random.gauss(1.0, 0.08)

                # Random event (5% chance of emergency each month)
                if random.random() < 0.05:
                    emergency = random.uniform(200, 2000)
                    savings -= emergency

                savings += monthly_inc - monthly_exp
                trajectory.append(round(savings, 2))

            simulations.append(trajectory)

        # Analyze results
        final_savings = [s[-1] for s in simulations]
        final_sorted = sorted(final_savings)

        return {
            "months_simulated": months,
            "scenarios_applied": scenarios,
            "current_savings": self.current_savings,
            "projections": {
                "pessimistic": final_sorted[10],   # 10th percentile
                "conservative": final_sorted[25],   # 25th percentile
                "expected": final_sorted[50],       # median
                "optimistic": final_sorted[75],     # 75th percentile
                "best_case": final_sorted[90],      # 90th percentile
            },
            "risk_of_negative": sum(1 for s in final_savings if s < 0) / len(final_savings) * 100,
            "average_final": round(sum(final_savings) / len(final_savings), 2),
        }

    def what_if(self, scenario_name: str, params: dict = None) -> dict:
        """Run specific what-if scenarios."""
        params = params or {}

        scenarios = {
            "job_loss": {"income_change": -1.0, "expense_change": -0.2},
            "raise_10": {"income_change": 0.1},
            "raise_25": {"income_change": 0.25},
            "emergency_5k": {"one_time_event": 5000},
            "emergency_10k": {"one_time_event": 10000},
            "frugal": {"expense_change": -0.3},
            "lavish": {"expense_change": 0.3},
            "side_hustle": {"income_change": 0.15},
            "custom": params,
        }

        scenario = scenarios.get(scenario_name, params)
        return self.simulate_months(months=12, scenarios=scenario)

    def recommend(self) -> list[dict]:
        """Generate personalized financial recommendations."""
        recs = []

        if self.savings_rate < 10:
            recs.append({
                "priority": "critical",
                "area": "savings",
                "message": f"Your savings rate is {self.savings_rate:.1f}%. Aim for at least 20%.",
                "action": "Reduce discretionary spending or find additional income.",
            })

        if self.current_savings < self.total_monthly_expenses * 3:
            recs.append({
                "priority": "high",
                "area": "emergency_fund",
                "message": f"Emergency fund covers {self.current_savings / self.total_monthly_expenses:.1f} months. Target: 3-6 months.",
                "action": "Prioritize building emergency fund before investing.",
            })

        total_debt = sum(float(d.get("amount", 0)) for d in self.debts)
        if total_debt > self.monthly_income * 6:
            recs.append({
                "priority": "high",
                "area": "debt",
                "message": f"Total debt ${total_debt:.0f} is {total_debt / self.monthly_income:.1f}x monthly income.",
                "action": "Focus on high-interest debt first (avalanche method).",
            })

        # Top expense category
        if self._category_totals:
            top_cat = max(self._category_totals.items(), key=lambda x: x[1])
            if top_cat[1] > self.total_monthly_expenses * 0.4:
                recs.append({
                    "priority": "medium",
                    "area": "spending",
                    "message": f"{top_cat[0]} accounts for {top_cat[1] / self.total_monthly_expenses * 100:.0f}% of spending.",
                    "action": f"Consider setting a budget cap for {top_cat[0]}.",
                })

        if not recs:
            recs.append({
                "priority": "low",
                "area": "optimization",
                "message": "Your finances look healthy!",
                "action": "Consider diversifying investments for long-term growth.",
            })

        return recs
