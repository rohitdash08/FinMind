"""
Financial Health Score Service

Computes a dynamic 0-100 health score based on:
  - Savings strength (income vs expense ratio)
  - Spending stability (coefficient of variation over recent months)
  - Bill reliability (on-time payment rate from bills data)
  - Trend direction (month-over-month expense trajectory)
"""

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Expense, Bill


@dataclass
class HealthBreakdown:
    savings_score: float  # 0-25
    stability_score: float  # 0-25
    reliability_score: float  # 0-25
    trend_score: float  # 0-25
    total: float  # 0-100
    grade: str  # A-F
    insights: list[dict]


def compute_health_score(user_id: int, months: int = 6) -> dict:
    """Main entry point. Returns full health score breakdown."""
    today = date.today()
    current_ym = today.strftime("%Y-%m")

    # Gather monthly data
    monthly_data = _get_monthly_data(user_id, months)

    active_months = [m for m in monthly_data if m["expenses"] > 0 or m["income"] > 0]
    if not active_months or len(active_months) < 2:
        return _empty_result("Insufficient data — need at least 2 months of history")

    # Component scores
    savings = _calc_savings_strength(active_months)
    stability = _calc_spending_stability(active_months)
    reliability = _calc_bill_reliability(user_id, months)
    trend = _calc_trend_direction(active_months)

    total = round(savings + stability + reliability + trend, 1)
    total = max(0.0, min(100.0, total))
    grade = _score_to_grade(total)
    insights = _generate_insights(active_months, savings, stability, reliability, trend)

    return {
        "score": total,
        "grade": grade,
        "breakdown": {
            "savings_strength": {
                "value": savings,
                "max": 25.0,
                "label": "Savings Strength",
                "description": "How much income you save vs spend",
            },
            "spending_stability": {
                "value": stability,
                "max": 25.0,
                "label": "Spending Stability",
                "description": "Consistency of monthly spending",
            },
            "bill_reliability": {
                "value": reliability,
                "max": 25.0,
                "label": "Bill Reliability",
                "description": "On-time bill payment rate",
            },
            "trend_direction": {
                "value": trend,
                "max": 25.0,
                "label": "Trend Direction",
                "description": "Whether spending is improving or worsening",
            },
        },
        "insights": insights,
        "months_analyzed": len(monthly_data),
    }


# ── Private helpers ──────────────────────────────────────────────


def _empty_result(reason: str) -> dict:
    return {
        "score": 0,
        "grade": "N/A",
        "breakdown": {},
        "insights": [{"type": "warning", "message": reason}],
        "months_analyzed": 0,
    }


def _get_monthly_data(user_id: int, months: int) -> list[dict]:
    """Fetch monthly income/expense totals from the database."""
    today = date.today()
    data = []
    for i in range(months, -1, -1):
        d = today.replace(day=1)
        # Walk back i months
        for _ in range(i):
            if d.month == 1:
                d = d.replace(year=d.year - 1, month=12)
            else:
                d = d.replace(month=d.month - 1)

        year, month = d.year, d.month
        income = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type == "INCOME",
            )
            .scalar()
        )
        expenses = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar()
        )
        data.append(
            {
                "ym": f"{year:04d}-{month:02d}",
                "income": float(income or 0),
                "expenses": float(expenses or 0),
                "net": float(income or 0) - float(expenses or 0),
            }
        )
    return data


def _calc_savings_strength(data: list[dict]) -> float:
    """
    Score 0-25 based on average savings rate.
    Savings rate = (income - expenses) / income
    """
    rates = []
    for m in data:
        if m["income"] > 0:
            rate = (m["income"] - m["expenses"]) / m["income"]
            rates.append(rate)

    if not rates:
        return 0.0

    avg_rate = sum(rates) / len(rates)

    # Scale: 0% savings = 0, 20% = 12.5, 30% = 18.75, 50%+ = 25
    if avg_rate >= 0.50:
        return 25.0
    elif avg_rate >= 0.30:
        return 18.75 + (avg_rate - 0.30) * (6.25 / 0.20)
    elif avg_rate >= 0.20:
        return 12.5 + (avg_rate - 0.20) * (6.25 / 0.10)
    elif avg_rate >= 0.10:
        return 6.25 + (avg_rate - 0.10) * (6.25 / 0.10)
    elif avg_rate >= 0.00:
        return avg_rate * (6.25 / 0.10)
    else:
        return 0.0


def _calc_spending_stability(data: list[dict]) -> float:
    """
    Score 0-25 based on spending consistency (low variance = high score).
    Uses coefficient of variation (CV) of monthly expenses.
    """
    expenses = [m["expenses"] for m in data if m["expenses"] > 0]
    if len(expenses) < 2:
        return 20.0  # Insufficient data to judge instability

    mean = sum(expenses) / len(expenses)
    if mean == 0:
        return 25.0

    variance = sum((e - mean) ** 2 for e in expenses) / len(expenses)
    std = math.sqrt(variance)
    cv = std / mean  # coefficient of variation

    # Scale: CV=0 (perfect stability) = 25, CV=0.5 = 12.5, CV>=1.0 = 0
    if cv >= 1.0:
        return 0.0
    elif cv >= 0.5:
        return max(0.0, 12.5 - (cv - 0.5) * 25.0)
    else:
        return 25.0 - cv * 25.0


def _calc_bill_reliability(user_id: int, months: int) -> float:
    """
    Score 0-25 based on active bill count and autopay coverage.
    Bills with autopay enabled = reliable. Active bills = engaged user.
    """
    from ..models import BillCadence

    today = date.today()

    try:
        active_bills = (
            db.session.query(Bill)
            .filter(Bill.user_id == user_id, Bill.active.is_(True))
            .all()
        )
    except Exception:
        return 12.5  # Default if query fails

    if not active_bills:
        return 15.0  # No bills = neutral score (not necessarily good or bad)

    autopay_count = sum(1 for b in active_bills if b.autopay_enabled)
    autopay_ratio = autopay_count / len(active_bills) if active_bills else 0

    # Check how many bills are overdue (past due date)
    overdue = sum(1 for b in active_bills if b.next_due_date < today)
    overdue_ratio = overdue / len(active_bills) if active_bills else 0

    # Score: autopay coverage gives base score, overdue bills reduce it
    base = autopay_ratio * 20.0
    penalty = overdue_ratio * 10.0
    score = max(0.0, base + 5.0 - penalty)  # 5.0 base for having any bills tracked

    return min(25.0, score)


def _calc_trend_direction(data: list[dict]) -> float:
    """
    Score 0-25 based on month-over-month expense trend.
    Decreasing expenses = higher score.
    Uses linear regression slope normalized by mean.
    """
    if len(data) < 3:
        return 15.0  # Neutral if insufficient data

    expenses = [m["expenses"] for m in data]
    n = len(expenses)

    # Simple linear regression: slope
    x_mean = (n - 1) / 2
    y_mean = sum(expenses) / n
    numerator = sum((i - x_mean) * (e - y_mean) for i, e in enumerate(expenses))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 15.0

    slope = numerator / denominator

    # Normalize by mean expense
    if y_mean > 0:
        slope_pct = slope / y_mean  # e.g., -0.05 means decreasing 5% per month
    else:
        return 15.0

    # Scale: negative slope (decreasing expenses) = high score
    # slope_pct <= -0.05 (decreasing 5%/month) = 25
    # slope_pct = 0 (stable) = 15
    # slope_pct >= +0.10 (increasing 10%/month) = 0
    if slope_pct <= -0.05:
        return 25.0
    elif slope_pct < 0:
        return 15.0 + abs(slope_pct) * 200  # 15 + 10 = 25 at -0.05
    elif slope_pct == 0:
        return 15.0
    elif slope_pct < 0.10:
        return max(0.0, 15.0 - slope_pct * 150)
    else:
        return 0.0


def _score_to_grade(score: float) -> str:
    if score >= 90:
        return "A+"
    elif score >= 80:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 50:
        return "D"
    else:
        return "F"


def _generate_insights(
    data: list[dict],
    savings: float,
    stability: float,
    reliability: float,
    trend: float,
) -> list[dict]:
    insights = []

    # Savings insights
    if savings < 10:
        insights.append(
            {
                "type": "warning",
                "category": "savings",
                "message": "Savings rate is critically low. Aim for at least 20% of income saved.",
            }
        )
    elif savings < 18:
        insights.append(
            {
                "type": "info",
                "category": "savings",
                "message": "Good start on savings, but room to improve. Target 30%+ savings rate.",
            }
        )
    else:
        insights.append(
            {
                "type": "positive",
                "category": "savings",
                "message": "Strong savings rate! You're building financial resilience.",
            }
        )

    # Stability insights
    if stability < 10:
        insights.append(
            {
                "type": "warning",
                "category": "stability",
                "message": "Spending varies significantly month-to-month. Consider a budget to smooth out fluctuations.",
            }
        )
    elif stability >= 20:
        insights.append(
            {
                "type": "positive",
                "category": "stability",
                "message": "Very consistent spending pattern — good budgeting discipline.",
            }
        )

    # Trend insights
    if data and len(data) >= 2:
        latest = data[-1]["expenses"]
        previous = data[-2]["expenses"]
        if previous > 0:
            change_pct = ((latest - previous) / previous) * 100
            if change_pct > 10:
                insights.append(
                    {
                        "type": "warning",
                        "category": "trend",
                        "message": f"Expenses increased {change_pct:.0f}% last month. Review recent spending.",
                    }
                )
            elif change_pct < -10:
                insights.append(
                    {
                        "type": "positive",
                        "category": "trend",
                        "message": f"Expenses decreased {abs(change_pct):.0f}% last month. Great progress!",
                    }
                )

    # Reliability insights
    if reliability < 10:
        insights.append(
            {
                "type": "warning",
                "category": "bills",
                "message": "Enable autopay on bills to avoid missed payments and improve your score.",
            }
        )
    elif reliability >= 20:
        insights.append(
            {
                "type": "positive",
                "category": "bills",
                "message": "Excellent bill management with autopay configured.",
            }
        )

    return insights
