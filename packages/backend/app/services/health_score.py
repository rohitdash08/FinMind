"""Predictive Financial Health Score for FinMind (#90)."""
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Bill, Expense, RecurringExpense

logger = logging.getLogger("finmind.health")


class ScoreComponent:
    """Individual component of the financial health score."""
    def __init__(self, name: str, score: float, weight: float, label: str, detail: str):
        self.name = name
        self.score = round(max(0.0, min(100.0, score)), 1)
        self.weight = weight
        self.label = label
        self.detail = detail

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "weighted_score": round(self.score * self.weight, 2),
            "label": self.label,
            "detail": self.detail,
        }


def _savings_strength_score(uid: int, months: int = 3) -> ScoreComponent:
    """Score 0-100 based on average savings rate vs income."""
    cutoff = date.today() - timedelta(days=30 * months)

    income = float(db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.user_id == uid,
        Expense.spent_at >= cutoff,
        Expense.expense_type == "INCOME",
    ).scalar() or 0) / months

    expenses = float(db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.user_id == uid,
        Expense.spent_at >= cutoff,
        Expense.expense_type != "INCOME",
    ).scalar() or 0) / months

    if income <= 0:
        return ScoreComponent(
            "savings_strength", 0, 0.30,
            "insufficient_data",
            "No income data found for scoring period"
        )

    savings_rate = max(0, (income - expenses) / income)
    score = min(100, savings_rate * 500)  # 20% savings = 100

    if savings_rate >= 0.20:
        label = "excellent"
    elif savings_rate >= 0.10:
        label = "good"
    elif savings_rate >= 0.05:
        label = "fair"
    else:
        label = "poor"

    return ScoreComponent(
        "savings_strength", score, 0.30, label,
        f"Saving {round(savings_rate * 100, 1)}% of income (avg {months} months)"
    )


def _spending_stability_score(uid: int, months: int = 3) -> ScoreComponent:
    """Score 0-100 based on consistency of monthly spending (low volatility = high score)."""
    monthly_expenses = []
    for i in range(months):
        ref = date.today() - timedelta(days=30 * i)
        total = float(db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == ref.year,
            extract("month", Expense.spent_at) == ref.month,
            Expense.expense_type != "INCOME",
        ).scalar() or 0)
        monthly_expenses.append(total)

    if not any(monthly_expenses):
        return ScoreComponent(
            "spending_stability", 0, 0.25,
            "insufficient_data",
            "No spending data found"
        )

    avg = sum(monthly_expenses) / len(monthly_expenses)
    if avg == 0:
        return ScoreComponent("spending_stability", 100, 0.25, "excellent", "No expenses tracked")

    variance = sum((x - avg) ** 2 for x in monthly_expenses) / len(monthly_expenses)
    cv = (variance ** 0.5) / avg  # Coefficient of variation

    # CV < 0.1 = excellent, > 0.5 = poor
    score = max(0, 100 - (cv * 200))

    if cv < 0.1:
        label = "excellent"
    elif cv < 0.25:
        label = "good"
    elif cv < 0.4:
        label = "fair"
    else:
        label = "poor"

    return ScoreComponent(
        "spending_stability", score, 0.25, label,
        f"Spending variation coefficient: {round(cv * 100, 1)}%"
    )


def _bill_reliability_score(uid: int) -> ScoreComponent:
    """Score 0-100 based on bills paid on time vs overdue."""
    today = date.today()
    total_bills = db.session.query(func.count(Bill.id)).filter(
        Bill.user_id == uid,
        Bill.active == True,
    ).scalar() or 0

    if total_bills == 0:
        return ScoreComponent(
            "bill_reliability", 50, 0.25,
            "no_data",
            "No bills tracked"
        )

    overdue_bills = db.session.query(func.count(Bill.id)).filter(
        Bill.user_id == uid,
        Bill.active == True,
        Bill.next_due_date < today,
    ).scalar() or 0

    on_time_rate = (total_bills - overdue_bills) / total_bills
    score = on_time_rate * 100

    if on_time_rate == 1.0:
        label = "excellent"
    elif on_time_rate >= 0.9:
        label = "good"
    elif on_time_rate >= 0.75:
        label = "fair"
    else:
        label = "poor"

    return ScoreComponent(
        "bill_reliability", score, 0.25, label,
        f"{total_bills - overdue_bills}/{total_bills} bills current (not overdue)"
    )


def _trend_direction_score(uid: int, months: int = 3) -> ScoreComponent:
    """Score 0-100 based on whether savings trend is improving."""
    nets = []
    for i in range(months + 2):
        ref = date.today() - timedelta(days=30 * i)
        inc = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == ref.year,
            extract("month", Expense.spent_at) == ref.month,
            Expense.expense_type == "INCOME",
        ).scalar() or 0)
        exp = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == ref.year,
            extract("month", Expense.spent_at) == ref.month,
            Expense.expense_type != "INCOME",
        ).scalar() or 0)
        nets.append(inc - exp)

    nets.reverse()  # Chronological

    if len(nets) < 2:
        return ScoreComponent("trend_direction", 50, 0.20, "insufficient_data", "Need more data for trend")

    # Simple slope: is the trend improving?
    n = len(nets)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(nets) / n
    num = sum((xs[i] - mean_x) * (nets[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0

    # Normalize slope to 0-100 score
    # Positive slope = good, negative = bad
    if mean_y != 0:
        relative_slope = slope / abs(mean_y)
    else:
        relative_slope = slope

    score = 50 + (relative_slope * 200)  # Clamp to 0-100
    score = max(0, min(100, score))

    if slope > 0:
        label = "improving"
    elif slope < 0:
        label = "declining"
    else:
        label = "stable"

    return ScoreComponent(
        "trend_direction", score, 0.20, label,
        f"Net savings trend: {'+' if slope > 0 else ''}{round(slope, 0)}/month"
    )


def calculate_health_score(uid: int, months: int = 3) -> dict:
    """
    Calculate a composite financial health score (0-100).

    Components:
    - Savings Strength (30%): avg savings rate vs income
    - Spending Stability (25%): monthly expense variance
    - Bill Reliability (25%): on-time bill payment rate
    - Trend Direction (20%): improving/declining net savings

    Returns:
        {
            "score": 0-100,
            "grade": "A" | "B" | "C" | "D" | "F",
            "label": "excellent" | "good" | "fair" | "poor",
            "components": [...],
            "insights": [...],
            "calculated_at": "YYYY-MM-DD"
        }
    """
    components = [
        _savings_strength_score(uid, months),
        _spending_stability_score(uid, months),
        _bill_reliability_score(uid),
        _trend_direction_score(uid, months),
    ]

    # Weighted composite score
    total_weight = sum(c.weight for c in components)
    composite = sum(c.score * c.weight for c in components) / total_weight

    # Grade
    if composite >= 85:
        grade, label = "A", "excellent"
    elif composite >= 70:
        grade, label = "B", "good"
    elif composite >= 55:
        grade, label = "C", "fair"
    elif composite >= 40:
        grade, label = "D", "needs_attention"
    else:
        grade, label = "F", "poor"

    # Insights
    insights = []
    worst = min(components, key=lambda c: c.score)
    best = max(components, key=lambda c: c.score)

    if worst.score < 50:
        insights.append(f"Focus area: {worst.name.replace("_", " ").title()} - {worst.detail}")
    if best.score >= 80:
        insights.append(f"Strength: {best.name.replace("_", " ").title()} - {best.detail}")

    logger.info("Health score uid=%s score=%.1f grade=%s", uid, composite, grade)

    return {
        "score": round(composite, 1),
        "grade": grade,
        "label": label,
        "components": [c.to_dict() for c in components],
        "insights": insights,
        "calculated_at": str(date.today()),
    }
