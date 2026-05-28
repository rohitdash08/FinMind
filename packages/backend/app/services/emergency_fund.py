"""Emergency Fund Calculator.

Features:
- Recommended fund size based on expenses
- Progress tracking
- Monthly savings plan
- Risk-based recommendations
- Scenario analysis (job loss, medical, etc.)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("finmind.emergency_fund")


class EmergencyFundService:

    def calculate_recommended(self, monthly_expenses: float,
                                monthly_income: float,
                                dependents: int = 0,
                                job_stability: str = "medium",
                                has_insurance: bool = True) -> dict:
        """Calculate recommended emergency fund size."""
        months_map = {
            "high": 3,
            "medium": 6,
            "low": 9,
            "freelance": 12,
        }
        base_months = months_map.get(job_stability, 6)

        # Adjust for dependents
        base_months += min(dependents, 4)

        # Adjust for insurance
        if not has_insurance:
            base_months += 3

        recommended = monthly_expenses * base_months
        minimum = monthly_expenses * 3
        comfortable = monthly_expenses * 9

        return {
            "monthly_expenses": round(monthly_expenses, 2),
            "monthly_income": round(monthly_income, 2),
            "job_stability": job_stability,
            "dependents": dependents,
            "recommended_months": base_months,
            "minimum_fund": round(minimum, 2),
            "recommended_fund": round(recommended, 2),
            "comfortable_fund": round(comfortable, 2),
            "fund_to_income_ratio": round(recommended / max(monthly_income, 1), 2),
        }

    def track_progress(self, current_savings: float,
                         monthly_expenses: float,
                         monthly_income: float,
                         monthly_contribution: float = None) -> dict:
        """Track emergency fund progress."""
        target = monthly_expenses * 6
        progress_pct = min(current_savings / max(target, 1) * 100, 100)
        shortfall = max(target - current_savings, 0)

        if monthly_contribution is None:
            monthly_contribution = max(monthly_income - monthly_expenses, 0) * 0.5

        months_to_goal = 0
        if monthly_contribution > 0 and shortfall > 0:
            months_to_goal = int(shortfall / monthly_contribution) + 1

        if progress_pct >= 100:
            status = "complete"
        elif progress_pct >= 75:
            status = "almost_there"
        elif progress_pct >= 50:
            status = "halfway"
        elif progress_pct >= 25:
            status = "building"
        else:
            status = "just_started"

        return {
            "current_savings": round(current_savings, 2),
            "target": round(target, 2),
            "shortfall": round(shortfall, 2),
            "progress_percent": round(progress_pct, 1),
            "status": status,
            "monthly_contribution": round(monthly_contribution, 2),
            "months_to_goal": months_to_goal,
            "goal_date": (datetime.utcnow() + timedelta(days=30 * months_to_goal)).isoformat()[:10] if months_to_goal > 0 else "N/A",
        }

    def savings_plan(self, target_amount: float, current_savings: float,
                       timeframe_months: int,
                       monthly_income: float,
                       monthly_expenses: float) -> dict:
        """Create a savings plan to reach emergency fund goal."""
        shortfall = max(target_amount - current_savings, 0)
        monthly_needed = shortfall / max(timeframe_months, 1)
        available = monthly_income - monthly_expenses
        feasible = monthly_needed <= available

        return {
            "target_amount": round(target_amount, 2),
            "current_savings": round(current_savings, 2),
            "shortfall": round(shortfall, 2),
            "timeframe_months": timeframe_months,
            "monthly_needed": round(monthly_needed, 2),
            "monthly_available": round(available, 2),
            "feasible": feasible,
            "savings_rate": round(monthly_needed / max(monthly_income, 1) * 100, 1),
            "recommendation": "increase_income" if not feasible else "on_track",
            "suggested_cutbacks": round(max(monthly_needed - available, 0), 2),
        }

    def scenario_analysis(self, monthly_expenses: float,
                            emergency_fund: float,
                            scenario: str = "job_loss") -> dict:
        """Analyze how long emergency fund lasts in different scenarios."""
        scenarios = {
            "job_loss": {"expense_multiplier": 0.7, "income": 0,
                         "description": "Complete job loss with reduced expenses"},
            "medical": {"expense_multiplier": 1.5, "income": 0.5,
                        "description": "Medical emergency with partial income"},
            "car_repair": {"expense_multiplier": 1.3, "income": 1.0,
                          "description": "Major car repair with full income"},
            "home_repair": {"expense_multiplier": 1.4, "income": 1.0,
                           "description": "Emergency home repair with full income"},
            "reduced_hours": {"expense_multiplier": 1.0, "income": 0.6,
                             "description": "Reduced working hours"},
        }

        s = scenarios.get(scenario, scenarios["job_loss"])
        adjusted_expenses = monthly_expenses * s["expense_multiplier"]
        monthly_shortfall = adjusted_expenses - (monthly_expenses * 2 * s["income"])

        if monthly_shortfall <= 0:
            months_covered = float("inf")
        else:
            months_covered = emergency_fund / monthly_shortfall

        return {
            "scenario": scenario,
            "description": s["description"],
            "monthly_expenses_adjusted": round(adjusted_expenses, 2),
            "monthly_income_fraction": round(s["income"] * 100, 0),
            "monthly_shortfall": round(max(monthly_shortfall, 0), 2),
            "fund_months_covered": round(months_covered, 1) if months_covered != float("inf") else "unlimited",
            "adequate": months_covered >= 3,
        }
