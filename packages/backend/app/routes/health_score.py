"""
Financial Health Score — computes a 0-100 composite score from four metrics:

  1. Savings Rate      (0-25 pts) – (income - expenses) / income for the month
  2. Spending Stability (0-25 pts) – inverse of daily-spend std-dev over 30 days
  3. Bill Reliability  (0-25 pts) – fraction of bills not overdue / total active
  4. Trend Score       (0-25 pts) – month-over-month expense improvement

Grades: A (>=80), B (>=65), C (>=50), D (>=35), F (<35)
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import extract, func

from ..extensions import db
from ..models import Bill, Expense
from ..services.cache import cache_get, cache_set

bp = Blueprint("health_score", __name__)

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_TTL = 300  # 5 minutes


def _score_key(user_id: int) -> str:
    return f"health_score:{user_id}:current"


def _history_key(user_id: int) -> str:
    return f"health_score:{user_id}:history"


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _grade(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "F"


def _clamp(value: float, lo: float = 0.0, hi: float = 25.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Per-metric calculators
# ---------------------------------------------------------------------------

def _savings_rate_score(uid: int, year: int, month: int) -> dict[str, Any]:
    """0-25 pts. Scales linearly from 0% savings (0 pts) to >=20% savings (25 pts)."""
    income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
        or 0
    )
    expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
        or 0
    )
    if income <= 0:
        rate = 0.0
        points = 0.0
    else:
        rate = max(0.0, (income - expenses) / income)
        # Full marks at 20% savings rate
        points = _clamp(rate / 0.20 * 25)
    return {
        "points": round(points, 2),
        "max": 25,
        "detail": {
            "income": income,
            "expenses": expenses,
            "savings_rate_pct": round(rate * 100, 2),
        },
    }


def _spending_stability_score(uid: int) -> dict[str, Any]:
    """0-25 pts. Lower daily-spend std-dev relative to mean → higher score."""
    today = date.today()
    start = today - timedelta(days=29)

    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("day_total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= today,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .all()
    )

    if not rows:
        return {"points": 12.5, "max": 25, "detail": {"cv": None, "days_with_data": 0}}

    daily_totals = [float(r.day_total) for r in rows]
    mean = sum(daily_totals) / len(daily_totals)

    if mean <= 0:
        return {"points": 25.0, "max": 25, "detail": {"cv": 0.0, "days_with_data": len(daily_totals)}}

    variance = sum((x - mean) ** 2 for x in daily_totals) / len(daily_totals)
    std_dev = math.sqrt(variance)
    cv = std_dev / mean  # coefficient of variation

    # CV=0 → 25 pts, CV>=1.5 → 0 pts
    points = _clamp(max(0.0, (1 - cv / 1.5)) * 25)
    return {
        "points": round(points, 2),
        "max": 25,
        "detail": {
            "cv": round(cv, 4),
            "mean_daily_spend": round(mean, 2),
            "std_dev": round(std_dev, 2),
            "days_with_data": len(daily_totals),
        },
    }


def _bill_reliability_score(uid: int) -> dict[str, Any]:
    """0-25 pts. Fraction of active bills with next_due_date >= today (on time)."""
    today = date.today()
    bills = (
        db.session.query(Bill)
        .filter(Bill.user_id == uid, Bill.active.is_(True))
        .all()
    )
    if not bills:
        return {"points": 25.0, "max": 25, "detail": {"on_time": 0, "overdue": 0, "total": 0}}

    overdue = sum(1 for b in bills if b.next_due_date < today)
    on_time = len(bills) - overdue
    fraction = on_time / len(bills)
    points = _clamp(fraction * 25)
    return {
        "points": round(points, 2),
        "max": 25,
        "detail": {
            "on_time": on_time,
            "overdue": overdue,
            "total": len(bills),
        },
    }


def _trend_score(uid: int, year: int, month: int) -> dict[str, Any]:
    """0-25 pts. Month-over-month expense change; improvement = higher score."""

    def _monthly_expenses(y: int, m: int) -> float:
        return float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == y,
                extract("month", Expense.spent_at) == m,
                Expense.expense_type != "INCOME",
            )
            .scalar()
            or 0
        )

    # Previous month
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    current = _monthly_expenses(year, month)
    previous = _monthly_expenses(prev_year, prev_month)

    if previous <= 0:
        # No data for previous month — neutral score
        points = 12.5
        change_pct = None
    else:
        change_pct = (current - previous) / previous
        # -20% or better → 25 pts; +20% or worse → 0 pts
        # Linear interpolation across [-0.20, +0.20]
        normalized = (-change_pct + 0.20) / 0.40  # 0..1
        points = _clamp(normalized * 25)

    return {
        "points": round(points, 2),
        "max": 25,
        "detail": {
            "current_month_expenses": round(current, 2),
            "previous_month_expenses": round(previous, 2),
            "change_pct": round(change_pct * 100, 2) if change_pct is not None else None,
        },
    }


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _compute_score(uid: int) -> dict[str, Any]:
    today = date.today()
    year, month = today.year, today.month

    savings = _savings_rate_score(uid, year, month)
    stability = _spending_stability_score(uid)
    reliability = _bill_reliability_score(uid)
    trend = _trend_score(uid, year, month)

    total = savings["points"] + stability["points"] + reliability["points"] + trend["points"]

    return {
        "score": round(total, 1),
        "grade": _grade(total),
        "computed_at": today.isoformat(),
        "period": f"{year}-{month:02d}",
        "breakdown": {
            "savings_rate": savings,
            "spending_stability": stability,
            "bill_reliability": reliability,
            "trend": trend,
        },
    }


# ---------------------------------------------------------------------------
# Tips engine
# ---------------------------------------------------------------------------

_TIPS: dict[str, list[str]] = {
    "savings_rate": [
        "Try to save at least 20% of your monthly income — even small steps count.",
        "Review your largest expense categories and find one to reduce by 10%.",
        "Set up an automatic transfer to savings on pay-day to remove temptation.",
    ],
    "spending_stability": [
        "Large swings in daily spending often signal impulse purchases — review them.",
        "Creating a weekly spending budget can smooth out unpredictable days.",
        "Try a 24-hour rule before any non-essential purchase over a set threshold.",
    ],
    "bill_reliability": [
        "Enable autopay for recurring bills to avoid missed or late payments.",
        "Set a reminder 3 days before each bill's due date.",
        "Consolidate bill due-dates to the same week each month for easier tracking.",
    ],
    "trend": [
        "Your expenses are rising month-over-month — identify the main driver and act.",
        "Benchmark this month against your 3-month average to spot spending creep.",
        "Try a no-spend day once a week to reduce the overall monthly total.",
    ],
}

_GENERAL_TIPS = [
    "Keep up the great work — your financial health is on track.",
    "Consider reviewing your financial goals quarterly.",
]


def _generate_tips(breakdown: dict[str, Any]) -> list[str]:
    """Return tips focused on the worst-scoring areas (below 60% of max)."""
    tips: list[str] = []
    sorted_metrics = sorted(
        breakdown.items(),
        key=lambda kv: kv[1]["points"] / kv[1]["max"],
    )
    for metric_key, metric_data in sorted_metrics:
        ratio = metric_data["points"] / metric_data["max"]
        if ratio < 0.60 and metric_key in _TIPS:
            tips.extend(_TIPS[metric_key][:2])
    if not tips:
        tips = _GENERAL_TIPS
    return tips[:6]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.get("")
@jwt_required()
def get_health_score():
    """Return the current financial health score with a full breakdown."""
    uid = int(get_jwt_identity())
    key = _score_key(uid)
    cached = cache_get(key)
    if cached:
        return jsonify(cached)

    result = _compute_score(uid)
    cache_set(key, result, ttl_seconds=_TTL)
    return jsonify(result)


@bp.get("/history")
@jwt_required()
def get_health_score_history():
    """Return monthly health scores for the past 6 months."""
    uid = int(get_jwt_identity())
    key = _history_key(uid)
    cached = cache_get(key)
    if cached:
        return jsonify(cached)

    today = date.today()
    history = []
    for delta in range(6):
        # Walk backwards month by month
        if today.month - delta < 1:
            m = today.month - delta + 12
            y = today.year - 1
        else:
            m = today.month - delta
            y = today.year

        savings = _savings_rate_score(uid, y, m)
        trend = _trend_score(uid, y, m)
        # For history use current stability/reliability (rolling 30 days)
        if delta == 0:
            stability = _spending_stability_score(uid)
            reliability = _bill_reliability_score(uid)
        else:
            # Approximate for past months — stability/reliability are rolling
            stability = {"points": 12.5, "max": 25}
            reliability = {"points": 12.5, "max": 25}

        total = (
            savings["points"]
            + stability["points"]
            + reliability["points"]
            + trend["points"]
        )
        history.append(
            {
                "period": f"{y}-{m:02d}",
                "score": round(total, 1),
                "grade": _grade(total),
                "breakdown": {
                    "savings_rate_pts": savings["points"],
                    "spending_stability_pts": stability["points"],
                    "bill_reliability_pts": reliability["points"],
                    "trend_pts": trend["points"],
                },
            }
        )

    history.reverse()  # oldest → newest
    payload = {"history": history}
    cache_set(key, payload, ttl_seconds=_TTL)
    return jsonify(payload)


@bp.get("/tips")
@jwt_required()
def get_health_score_tips():
    """Return actionable tips based on the lowest-scoring areas."""
    uid = int(get_jwt_identity())
    # Reuse cached score if available
    key = _score_key(uid)
    cached = cache_get(key)
    if cached:
        breakdown = cached["breakdown"]
    else:
        result = _compute_score(uid)
        cache_set(key, result, ttl_seconds=_TTL)
        breakdown = result["breakdown"]

    tips = _generate_tips(breakdown)
    return jsonify({"tips": tips, "count": len(tips)})
