"""Predictive Financial Health Score for FinMind.

Dynamic score (0-100) based on:
- Savings Strength (25%): savings rate, emergency fund coverage
- Spending Stability (25%): consistency, volatility
- Bill Reliability (25%): on-time payments, no missed bills
- Trend Direction (25%): improving vs deteriorating

Each dimension scored 0-100, weighted into composite score.
Includes trend analysis and actionable recommendations.
"""

import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional

from ..extensions import db

logger = logging.getLogger("finmind.health_score")


class HealthDimension:
    """A single dimension of financial health."""

    def __init__(self, name: str, score: float, weight: float,
                 details: dict = None, recommendation: str = None):
        self.name = name
        self.score = min(max(score, 0), 100)  # Clamp 0-100
        self.weight = weight
        self.details = details or {}
        self.recommendation = recommendation or ""

    def to_dict(self):
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "weight": self.weight,
            "weighted_score": round(self.score * self.weight, 1),
            "details": self.details,
            "recommendation": self.recommendation,
        }


class FinancialHealthReport:
    """Complete financial health report."""

    def __init__(self, composite_score: float, dimensions: list[HealthDimension],
                 trend: str, recommendations: list[str]):
        self.composite_score = round(min(max(composite_score, 0), 100), 1)
        self.dimensions = dimensions
        self.trend = trend  # "improving", "stable", "declining"
        self.recommendations = recommendations
        self.generated_at = datetime.now(timezone.utc)

    @property
    def grade(self) -> str:
        if self.composite_score >= 90:
            return "A+"
        elif self.composite_score >= 80:
            return "A"
        elif self.composite_score >= 70:
            return "B"
        elif self.composite_score >= 60:
            return "C"
        elif self.composite_score >= 50:
            return "D"
        return "F"

    def to_dict(self):
        return {
            "composite_score": self.composite_score,
            "grade": self.grade,
            "trend": self.trend,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "recommendations": self.recommendations,
            "generated_at": self.generated_at.isoformat(),
        }


def _calc_savings_strength(income: float, expenses: list[dict],
                           savings_goal: float = None) -> HealthDimension:
    """Score savings strength (0-100).

    Factors:
    - Savings rate (income - expenses) / income
    - Emergency fund coverage (months of expenses)
    """
    total_expenses = sum(float(e.get("amount", 0)) for e in expenses)

    if income <= 0:
        return HealthDimension("Savings Strength", 10, 0.25,
                              {"savings_rate": 0, "months_coverage": 0},
                              "Add your income to get a savings assessment")

    savings = income - total_expenses
    savings_rate = savings / income * 100 if income else 0
    monthly_expenses = total_expenses / max(len(expenses), 1) * 30  # Approx monthly
    months_coverage = savings / monthly_expenses if monthly_expenses > 0 else 0

    # Score calculation
    score = 30  # Base score
    if savings_rate > 0:
        score += min(savings_rate * 1.5, 40)  # Up to 40 pts for savings rate
    if months_coverage >= 6:
        score += 30  # Full marks for 6+ months coverage
    elif months_coverage >= 3:
        score += 20
    elif months_coverage >= 1:
        score += 10

    recommendation = ""
    if savings_rate < 10:
        recommendation = "Try to save at least 10% of income. Consider cutting non-essential spending."
    elif months_coverage < 3:
        recommendation = f"Emergency fund covers {months_coverage:.1f} months. Aim for 3-6 months."
    elif savings_rate >= 20:
        recommendation = "Excellent savings rate! Consider investing surplus for long-term growth."

    return HealthDimension("Savings Strength", score, 0.25,
                          {"savings_rate": round(savings_rate, 1),
                           "monthly_savings": round(savings, 2),
                           "months_coverage": round(months_coverage, 1)},
                          recommendation)


def _calc_spending_stability(expenses: list[dict], period_months: int = 3) -> HealthDimension:
    """Score spending stability (0-100).

    Lower volatility = higher score.
    """
    if not expenses:
        return HealthDimension("Spending Stability", 50, 0.25,
                              {"volatility": 0}, "Add transactions to track stability")

    # Group by month
    monthly = defaultdict(float)
    for e in expenses:
        date_str = e.get("date", "")
        if isinstance(date_str, str) and len(date_str) >= 7:
            month_key = date_str[:7]
            monthly[month_key] += float(e.get("amount", 0))

    amounts = list(monthly.values())
    if len(amounts) < 2:
        return HealthDimension("Spending Stability", 60, 0.25,
                              {"volatility": 0, "note": "Need 2+ months of data"})

    avg = sum(amounts) / len(amounts)
    variance = sum((a - avg) ** 2 for a in amounts) / len(amounts)
    std_dev = variance ** 0.5
    coefficient_of_variation = std_dev / avg if avg else 0

    # Score: low CV = high stability
    score = max(100 - coefficient_of_variation * 200, 10)

    recommendation = ""
    if coefficient_of_variation > 0.3:
        recommendation = "Spending is highly variable. Set budgets for top categories to stabilize."
    elif coefficient_of_variation > 0.15:
        recommendation = "Spending is moderately stable. Review months with spikes."

    return HealthDimension("Spending Stability", score, 0.25,
                          {"coefficient_of_variation": round(coefficient_of_variation, 3),
                           "monthly_average": round(avg, 2),
                           "std_deviation": round(std_dev, 2)},
                          recommendation)


def _calc_bill_reliability(bills: list[dict]) -> HealthDimension:
    """Score bill payment reliability (0-100).

    Factors: on-time rate, no missed payments.
    """
    if not bills:
        return HealthDimension("Bill Reliability", 70, 0.25,
                              {"on_time_rate": 1.0}, "No bills tracked yet")

    total = len(bills)
    paid_on_time = sum(1 for b in bills if b.get("status") == "paid")
    overdue = sum(1 for b in bills if b.get("status") == "overdue")
    missed = sum(1 for b in bills if b.get("status") == "missed")

    on_time_rate = paid_on_time / total if total else 0

    score = on_time_rate * 80  # Up to 80 pts for on-time rate
    if overdue > 0:
        score -= overdue * 5
    if missed > 0:
        score -= missed * 10
    score = max(score, 0)

    recommendation = ""
    if on_time_rate < 0.8:
        recommendation = f"Only {on_time_rate*100:.0f}% of bills paid on time. Set up reminders."
    elif overdue > 0:
        recommendation = f"{overdue} overdue bill(s). Pay immediately to avoid fees."

    return HealthDimension("Bill Reliability", score, 0.25,
                          {"total_bills": total,
                           "paid_on_time": paid_on_time,
                           "overdue": overdue,
                           "missed": missed,
                           "on_time_rate": round(on_time_rate, 3)},
                          recommendation)


def _calc_trend_direction(current_expenses: list[dict],
                          previous_expenses: list[dict],
                          income: float) -> HealthDimension:
    """Score trend direction (0-100).

    Improving trend = spending decreasing relative to income.
    """
    curr_total = sum(float(e.get("amount", 0)) for e in current_expenses)
    prev_total = sum(float(e.get("amount", 0)) for e in previous_expenses)

    if prev_total == 0:
        return HealthDimension("Trend Direction", 50, 0.25,
                              {"direction": "neutral"}, "Need historical data for trends")

    change_pct = ((curr_total - prev_total) / prev_total) * 100

    # Score: negative spending change (saving more) = higher score
    score = 50 - change_pct  # -20% change = 70, +20% change = 30
    score = min(max(score, 0), 100)

    if change_pct < -10:
        direction = "improving"
        recommendation = "Great progress! Spending decreased significantly."
    elif change_pct < 0:
        direction = "slightly_improving"
        recommendation = "Spending is trending down. Keep it up!"
    elif change_pct < 10:
        direction = "stable"
        recommendation = "Spending is relatively stable."
    else:
        direction = "declining"
        recommendation = f"Spending increased {change_pct:.0f}%. Review recent purchases."

    return HealthDimension("Trend Direction", score, 0.25,
                          {"spending_change_pct": round(change_pct, 1),
                           "current_total": round(curr_total, 2),
                           "previous_total": round(prev_total, 2),
                           "direction": direction},
                          recommendation)


def calculate_health_score(
    income: float = 0,
    expenses: list[dict] = None,
    previous_expenses: list[dict] = None,
    bills: list[dict] = None,
) -> FinancialHealthReport:
    """Calculate comprehensive financial health score.

    Args:
        income: Monthly income
        expenses: Current period transactions
        previous_expenses: Previous period transactions
        bills: List of bills with status field

    Returns:
        FinancialHealthReport with composite score and breakdown
    """
    expenses = expenses or []
    previous_expenses = previous_expenses or []
    bills = bills or []

    dimensions = [
        _calc_savings_strength(income, expenses),
        _calc_spending_stability(expenses),
        _calc_bill_reliability(bills),
        _calc_trend_direction(expenses, previous_expenses, income),
    ]

    composite = sum(d.score * d.weight for d in dimensions)

    # Determine overall trend
    trend_dim = dimensions[3]
    trend_data = trend_dim.details
    overall_trend = trend_data.get("direction", "stable")
    if overall_trend == "slightly_improving":
        overall_trend = "improving"

    # Collect recommendations
    recommendations = []
    for d in dimensions:
        if d.recommendation:
            recommendations.append(f"{d.name}: {d.recommendation}")

    # Add composite recommendation
    if composite < 50:
        recommendations.insert(0, "Focus on fundamentals: build emergency fund and pay bills on time.")
    elif composite < 70:
        recommendations.insert(0, "Good progress! Work on the weakest dimension above.")
    elif composite >= 85:
        recommendations.insert(0, "Excellent financial health! Maintain and consider investing.")

    return FinancialHealthReport(composite, dimensions, overall_trend, recommendations)
