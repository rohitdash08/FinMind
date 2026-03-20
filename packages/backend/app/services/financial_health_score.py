"""
Predictive Financial Health Score service.

Computes a composite score (0-100) from four weighted dimensions:
  - Savings Strength (30%): ratio of saved amount to income
  - Spending Stability (25%): coefficient of variation in monthly spending
  - Bill Reliability (25%): on-time bill payment rate
  - Trend Direction (20%): 3-month spending trend vs prior 3 months
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, datetime, timedelta
from sqlalchemy import func, extract
from collections import defaultdict
import math

from ..models import Expense, Bill, BillReminder


# Score weights
WEIGHT_SAVINGS = 0.30
WEIGHT_STABILITY = 0.25
WEIGHT_BILL_RELIABILITY = 0.25
WEIGHT_TREND = 0.20


@dataclass
class DimensionScore:
    name: str
    score: float          # 0-100
    weight: float         # contribution weight
    weighted_score: float # score * weight
    explanation: str


@dataclass
class FinancialHealthResult:
    overall_score: float            # 0-100
    grade: str                      # A/B/C/D/F
    summary: str
    dimensions: list[DimensionScore]
    months_analyzed: int
    computed_at: str


def _grade(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _summary(score: float) -> str:
    if score >= 85:
        return "Excellent financial health. Keep up the great habits."
    if score >= 70:
        return "Good financial health with room for improvement."
    if score >= 55:
        return "Fair financial health. Focus on savings and stability."
    if score >= 40:
        return "Below average. Review spending and bill payment habits."
    return "Poor financial health. Immediate action recommended."


def _monthly_totals(expenses: list, months: int) -> dict[str, float]:
    """Aggregate expense amounts by YYYY-MM key for last N months."""
    cutoff = date.today().replace(day=1) - timedelta(days=30 * months)
    totals: dict[str, float] = defaultdict(float)
    for exp in expenses:
        if hasattr(exp, 'date') and exp.date and exp.date >= cutoff:
            key = exp.date.strftime("%Y-%m")
            totals[key] += float(exp.amount)
    return dict(totals)


def _savings_score(expenses: list, months: int) -> tuple[float, str]:
    """
    Score savings strength based on average monthly spend relative to
    an assumed income proxy (90th-percentile monthly spend as upper bound).
    If user has income data we'd use it; here we approximate:
    - Avg spend < 60% of max month => strong savings (~80-100)
    - Avg spend 60-80% of max month => moderate (50-80)
    - Avg spend > 80% => weak (0-50)
    """
    totals = _monthly_totals(expenses, months)
    if not totals:
        return 50.0, "Not enough data to evaluate savings strength."

    values = list(totals.values())
    avg_spend = sum(values) / len(values)
    max_spend = max(values)

    if max_spend == 0:
        return 50.0, "No spending data found."

    ratio = avg_spend / max_spend  # lower is better (saving more in good months)
    # Map ratio [0, 1] -> score [100, 0]
    score = max(0.0, min(100.0, (1 - ratio) * 100 + 30))
    # Clamp: even ratio=1 (spend everything) gets 30, ratio=0 gets 130→100
    score = min(100.0, score)

    if score >= 75:
        explanation = f"Strong savings: average monthly spend is {ratio*100:.0f}% of peak."
    elif score >= 50:
        explanation = f"Moderate savings: average spend is {ratio*100:.0f}% of peak spending month."
    else:
        explanation = f"Weak savings: spending near maximum most months ({ratio*100:.0f}% of peak)."

    return round(score, 1), explanation


def _stability_score(expenses: list, months: int) -> tuple[float, str]:
    """
    Score spending stability using coefficient of variation (CV = std/mean).
    Lower CV = more stable = higher score.
    """
    totals = _monthly_totals(expenses, months)
    values = list(totals.values())

    if len(values) < 2:
        return 50.0, "Not enough months of data to assess stability."

    mean = sum(values) / len(values)
    if mean == 0:
        return 50.0, "No spending data."

    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    cv = std / mean  # 0 = perfect stability

    # Map CV [0, 1+] -> score [100, 0]
    # CV=0 -> 100, CV=0.5 -> ~50, CV=1+ -> ~0
    score = max(0.0, min(100.0, 100 * (1 - cv)))

    if score >= 75:
        explanation = f"Very stable spending (CV={cv:.2f}). Monthly expenses are consistent."
    elif score >= 50:
        explanation = f"Moderate spending volatility (CV={cv:.2f}). Some months vary significantly."
    else:
        explanation = f"High spending volatility (CV={cv:.2f}). Expenses fluctuate substantially."

    return round(score, 1), explanation


def _bill_reliability_score(user_id: int, months: int) -> tuple[float, str]:
    """
    Score bill reliability: ratio of paid bills to total due bills in period.
    """
    cutoff = datetime.utcnow() - timedelta(days=30 * months)
    total = Bill.query.filter(
        Bill.user_id == user_id,
        Bill.due_date >= cutoff.date(),
    ).count()

    if total == 0:
        return 75.0, "No bills found. Score neutral."

    paid = Bill.query.filter(
        Bill.user_id == user_id,
        Bill.due_date >= cutoff.date(),
        Bill.status == "paid",
    ).count()

    ratio = paid / total
    score = ratio * 100

    if score >= 90:
        explanation = f"Excellent bill reliability: {paid}/{total} bills paid on time."
    elif score >= 70:
        explanation = f"Good reliability: {paid}/{total} bills paid. {total - paid} missed/pending."
    else:
        explanation = f"Poor bill reliability: only {paid}/{total} paid. {total - paid} outstanding."

    return round(score, 1), explanation


def _trend_score(expenses: list) -> tuple[float, str]:
    """
    Score trend direction by comparing last 3 months vs prior 3 months.
    Improving (spending down) = high score. Worsening = low score.
    """
    totals = _monthly_totals(expenses, 6)
    sorted_months = sorted(totals.keys())

    if len(sorted_months) < 4:
        return 50.0, "Not enough history to detect spending trend."

    mid = len(sorted_months) // 2
    recent = sorted_months[mid:]
    prior = sorted_months[:mid]

    recent_avg = sum(totals[m] for m in recent) / len(recent) if recent else 0
    prior_avg = sum(totals[m] for m in prior) / len(prior) if prior else 0

    if prior_avg == 0:
        return 50.0, "No prior period data for trend comparison."

    change_pct = (recent_avg - prior_avg) / prior_avg  # negative = improvement

    # Map: -50%+ improvement -> 100, 0% change -> 50, +50% worse -> 0
    score = max(0.0, min(100.0, 50 - change_pct * 100))

    if score >= 70:
        explanation = f"Positive trend: spending decreased {-change_pct*100:.1f}% vs prior period."
    elif score >= 45:
        explanation = f"Neutral trend: spending changed {change_pct*100:+.1f}% vs prior period."
    else:
        explanation = f"Negative trend: spending increased {change_pct*100:.1f}% vs prior period."

    return round(score, 1), explanation


def get_financial_health_score(user_id: int, months: int = 6) -> FinancialHealthResult:
    """
    Compute comprehensive financial health score for a user.

    Args:
        user_id: User ID
        months: Number of months to analyze (default 6, max 24)

    Returns:
        FinancialHealthResult with overall score, grade, and per-dimension breakdown.
    """
    months = max(1, min(24, months))

    cutoff = datetime.utcnow() - timedelta(days=30 * months)
    expenses = Expense.query.filter(
        Expense.user_id == user_id,
        Expense.date >= cutoff.date(),
    ).all()

    # Compute each dimension
    sav_score, sav_exp = _savings_score(expenses, months)
    stab_score, stab_exp = _stability_score(expenses, months)
    bill_score, bill_exp = _bill_reliability_score(user_id, months)
    trend_score, trend_exp = _trend_score(expenses)

    # Weighted overall score
    overall = (
        sav_score * WEIGHT_SAVINGS
        + stab_score * WEIGHT_STABILITY
        + bill_score * WEIGHT_BILL_RELIABILITY
        + trend_score * WEIGHT_TREND
    )
    overall = round(overall, 1)

    dimensions = [
        DimensionScore(
            name="savings_strength",
            score=sav_score,
            weight=WEIGHT_SAVINGS,
            weighted_score=round(sav_score * WEIGHT_SAVINGS, 1),
            explanation=sav_exp,
        ),
        DimensionScore(
            name="spending_stability",
            score=stab_score,
            weight=WEIGHT_STABILITY,
            weighted_score=round(stab_score * WEIGHT_STABILITY, 1),
            explanation=stab_exp,
        ),
        DimensionScore(
            name="bill_reliability",
            score=bill_score,
            weight=WEIGHT_BILL_RELIABILITY,
            weighted_score=round(bill_score * WEIGHT_BILL_RELIABILITY, 1),
            explanation=bill_exp,
        ),
        DimensionScore(
            name="trend_direction",
            score=trend_score,
            weight=WEIGHT_TREND,
            weighted_score=round(trend_score * WEIGHT_TREND, 1),
            explanation=trend_exp,
        ),
    ]

    return FinancialHealthResult(
        overall_score=overall,
        grade=_grade(overall),
        summary=_summary(overall),
        dimensions=dimensions,
        months_analyzed=months,
        computed_at=datetime.utcnow().isoformat() + "Z",
    )