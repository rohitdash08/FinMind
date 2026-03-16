"""
Autonomous Budget Optimization service (Issue #92).

Analyses a user's spending history to detect overspending patterns,
recommend category-level reallocations, and return an adaptive budget
plan that improves over time as more data is available.

No external dependencies — pure Python + SQLAlchemy.

Public API:
    get_budget_optimization(uid, months) → BudgetOptimizationResult dict
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.budget_optimizer")

# ── Constants ─────────────────────────────────────────────────────────────────

# 50/30/20 rule targets (needs / wants / savings)
_TARGET_NEEDS_PCT = 0.50
_TARGET_WANTS_PCT = 0.30
_TARGET_SAVINGS_PCT = 0.20

# Overspend threshold: flag a category if its share of total expenses exceeds
# this multiple of its "fair share" across all categories
_OVERSPEND_MULTIPLIER = 1.5

# Minimum months of history required for trend analysis
_MIN_MONTHS_FOR_TREND = 2

# Maximum number of reallocation recommendations returned
_MAX_RECOMMENDATIONS = 5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _iter_months(anchor: date, n: int):
    """Yield (year, month) tuples for the last *n* months ending at anchor."""
    year, month = anchor.year, anchor.month
    for _ in range(n):
        yield year, month
        month -= 1
        if month == 0:
            month = 12
            year -= 1


def _monthly_category_spend(uid: int, year: int, month: int) -> dict[int | None, float]:
    """Return {category_id: total_amount} for EXPENSE rows in a given month."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "EXPENSE",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {row.category_id: float(row.total) for row in rows}


def _monthly_income(uid: int, year: int, month: int) -> float:
    total = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    return float(total or 0)


def _category_name(cat_id: int | None) -> str:
    if cat_id is None:
        return "Uncategorized"
    cat = db.session.get(Category, cat_id)
    return cat.name if cat else f"Category {cat_id}"


def _detect_overspending(
    cat_totals: dict[str, float],
    total_expenses: float,
) -> list[dict]:
    """Flag categories that consume a disproportionate share of spending."""
    if not cat_totals or total_expenses <= 0:
        return []

    n_cats = len(cat_totals)
    fair_share = total_expenses / n_cats if n_cats else 0
    threshold = fair_share * _OVERSPEND_MULTIPLIER

    flagged = []
    for cat_id_str, amount in sorted(cat_totals.items(), key=lambda x: -x[1]):
        if amount > threshold:
            pct = round(amount / total_expenses * 100, 1)
            flagged.append({
                "category_id": cat_id_str,
                "amount": round(amount, 2),
                "share_pct": pct,
                "threshold": round(threshold, 2),
                "excess": round(amount - threshold, 2),
            })
    return flagged


def _compute_trend(monthly_totals: list[float]) -> dict:
    """Compute MoM change and direction from a list of monthly totals (oldest→newest)."""
    if len(monthly_totals) < _MIN_MONTHS_FOR_TREND:
        return {"direction": "insufficient_data", "avg_mom_change_pct": None}

    changes = []
    for i in range(1, len(monthly_totals)):
        prev = monthly_totals[i - 1]
        curr = monthly_totals[i]
        if prev > 0:
            changes.append((curr - prev) / prev * 100)

    if not changes:
        return {"direction": "stable", "avg_mom_change_pct": 0.0}

    avg = round(sum(changes) / len(changes), 1)
    direction = "increasing" if avg > 2 else ("decreasing" if avg < -2 else "stable")
    return {"direction": direction, "avg_mom_change_pct": avg}


def _build_reallocations(
    cat_totals: dict[str, float],
    avg_income: float,
    overspent: list[dict],
) -> list[dict]:
    """
    Suggest concrete reallocations:
    - Trim each overspent category by 10%
    - Redirect the freed funds toward savings
    """
    recommendations: list[dict] = []

    for item in overspent[:_MAX_RECOMMENDATIONS]:
        trimmed = round(item["amount"] * 0.10, 2)
        recommendations.append({
            "type": "trim",
            "category_id": item["category_id"],
            "current_spend": item["amount"],
            "suggested_spend": round(item["amount"] - trimmed, 2),
            "savings_opportunity": trimmed,
            "reason": (
                f"This category accounts for {item['share_pct']}% of total expenses, "
                f"which is {round(item['amount'] / item['threshold'], 1)}× the average. "
                "A 10% reduction frees up funds for savings."
            ),
        })

    # If income is known, add a 50/30/20 target summary
    if avg_income > 0:
        recommendations.append({
            "type": "target_budget",
            "needs_target": round(avg_income * _TARGET_NEEDS_PCT, 2),
            "wants_target": round(avg_income * _TARGET_WANTS_PCT, 2),
            "savings_target": round(avg_income * _TARGET_SAVINGS_PCT, 2),
            "reason": "Based on the 50/30/20 rule applied to your average monthly income.",
        })

    return recommendations


# ── Public API ────────────────────────────────────────────────────────────────

def get_budget_optimization(
    uid: int,
    months: int = 3,
    anchor: date | None = None,
) -> dict[str, Any]:
    """
    Analyse the last *months* of expense history for *uid* and return an
    autonomous budget optimization plan.

    Returns a dict with keys:
        analysis_period      — months analysed
        monthly_breakdown    — per-month spend totals
        avg_monthly_expenses — average monthly spend over the period
        avg_monthly_income   — average monthly income over the period
        net_flow             — avg income − avg expenses
        trend                — spending direction + MoM change %
        overspending_alerts  — categories above the proportional threshold
        category_totals      — aggregated spend per category (IDs → names)
        recommendations      — list of reallocation / trim suggestions
        generated_at         — ISO timestamp
    """
    if anchor is None:
        anchor = date.today()

    months = max(1, min(months, 12))  # clamp to 1–12

    monthly_expenses: list[float] = []
    monthly_income: list[float] = []
    agg_cat_totals: dict[str | None, float] = {}  # category_id (str) → cumulative

    for year, month in _iter_months(anchor, months):
        cat_spend = _monthly_category_spend(uid, year, month)
        m_expense = sum(cat_spend.values())
        m_income = _monthly_income(uid, year, month)

        monthly_expenses.append(m_expense)
        monthly_income.append(m_income)

        for cat_id, amount in cat_spend.items():
            key = str(cat_id) if cat_id is not None else "uncat"
            agg_cat_totals[key] = agg_cat_totals.get(key, 0.0) + amount

    # Reverse so the list runs oldest → newest for trend calculation
    monthly_expenses.reverse()
    monthly_income.reverse()

    avg_expenses = round(sum(monthly_expenses) / months, 2) if months else 0.0
    avg_income = round(sum(monthly_income) / months, 2) if months else 0.0
    total_expenses = sum(monthly_expenses)

    # Resolve category names for the response
    cat_totals_named: dict[str, Any] = {}
    for key, amount in agg_cat_totals.items():
        cat_id = None if key == "uncat" else int(key)
        name = _category_name(cat_id)
        cat_totals_named[name] = round(amount, 2)

    # Detect overspending against avg monthly totals
    avg_cat_totals = {k: round(v / months, 2) for k, v in agg_cat_totals.items()}
    overspent = _detect_overspending(avg_cat_totals, avg_expenses)

    # Humanise overspent entries (add category name)
    for item in overspent:
        cat_id = None if item["category_id"] == "uncat" else (
            int(item["category_id"]) if item["category_id"].isdigit() else None
        )
        item["category_name"] = _category_name(cat_id)

    trend = _compute_trend(monthly_expenses)
    recommendations = _build_reallocations(avg_cat_totals, avg_income, overspent)

    # Build month labels for the breakdown (oldest → newest)
    period_months = list(reversed(list(_iter_months(anchor, months))))
    monthly_breakdown = [
        {
            "month": f"{y:04d}-{m:02d}",
            "expenses": round(monthly_expenses[i], 2),
            "income": round(monthly_income[i], 2),
            "net": round(monthly_income[i] - monthly_expenses[i], 2),
        }
        for i, (y, m) in enumerate(period_months)
    ]

    logger.info(
        "Budget optimization generated uid=%s months=%s avg_expenses=%s trend=%s",
        uid, months, avg_expenses, trend["direction"],
    )

    return {
        "analysis_period_months": months,
        "monthly_breakdown": monthly_breakdown,
        "avg_monthly_expenses": avg_expenses,
        "avg_monthly_income": avg_income,
        "net_flow": round(avg_income - avg_expenses, 2),
        "trend": trend,
        "overspending_alerts": overspent,
        "category_totals": cat_totals_named,
        "recommendations": recommendations,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
