"""
Explainable Spending Insights (Issue #89).

Provides human-readable explanations of WHY spending changed month-over-month:
- What changed (category-level delta detection)
- Why it changed (pattern-based explanation with confidence level)
- Confidence score based on data richness and change magnitude

Public API
----------
get_spending_insights(uid, months, anchor) → InsightsResult dict
"""

from __future__ import annotations

import logging
import statistics
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.insights_explainable")

# ── Constants ─────────────────────────────────────────────────────────────────

# Minimum % change to consider "significant"
_SIGNIFICANT_CHANGE_PCT = 15.0
# Minimum absolute change to surface (avoid noise on tiny amounts)
_MIN_ABSOLUTE_CHANGE = 50.0
# Confidence thresholds
_HIGH_CONF_MONTHS = 4
_MED_CONF_MONTHS  = 2


# ── Data helpers ──────────────────────────────────────────────────────────────

def _month_expense_by_category(uid: int, year: int, month: int) -> dict[int | None, float]:
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
    return {r.category_id: float(r.total) for r in rows}


def _month_totals(uid: int, year: int, month: int) -> tuple[float, float]:
    inc = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar() or 0
    )
    exp = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "EXPENSE",
        )
        .scalar() or 0
    )
    return inc, exp


def _category_name(cat_id: int | None) -> str:
    if cat_id is None:
        return "Uncategorized"
    cat = db.session.get(Category, cat_id)
    return cat.name if cat else f"Category {cat_id}"


def _iter_months_back(anchor: date, n: int):
    y, m = anchor.year, anchor.month
    for _ in range(n):
        yield y, m
        m -= 1
        if m == 0:
            m = 12
            y -= 1


# ── Explanation engine ────────────────────────────────────────────────────────

def _explain_change(
    cat_name: str,
    prev: float,
    curr: float,
    pct_change: float,
    history: list[float],
) -> tuple[str, str]:
    """
    Return (what_changed, why_it_changed) explanations for a category delta.
    Uses heuristics based on magnitude, direction, and historical variance.
    """
    direction = "increased" if curr > prev else "decreased"
    abs_pct = abs(pct_change)

    # Determine historical baseline volatility
    if len(history) >= 3:
        std = statistics.stdev(history)
        mean = statistics.mean(history)
        cv = std / mean if mean > 0 else 0  # coefficient of variation
    else:
        cv = 0

    what = (
        f"{cat_name} spending {direction} by {abs_pct:.1f}% "
        f"({abs(curr - prev):.2f} more)" if curr > prev
        else f"{cat_name} spending {direction} by {abs_pct:.1f}% "
             f"({abs(curr - prev):.2f} less)"
    )

    # Why heuristics
    if prev == 0 and curr > 0:
        why = f"New spending in {cat_name} this month — no previous activity recorded."
    elif curr == 0 and prev > 0:
        why = f"No {cat_name} expenses recorded this month (category went quiet)."
    elif abs_pct > 100:
        why = f"Exceptional spike in {cat_name} — spending more than doubled. Likely a one-time large purchase or irregular event."
    elif abs_pct > 50:
        why = f"Large change in {cat_name}. Could indicate a seasonal pattern, a big purchase, or a change in habits."
    elif cv > 0.4 and abs_pct > 20:
        why = f"{cat_name} is historically volatile (high month-to-month variance), so this change may be within the normal range."
    elif abs_pct > _SIGNIFICANT_CHANGE_PCT and cv < 0.2:
        why = f"{cat_name} is usually stable, making this change notable. Consider reviewing recent transactions in this category."
    else:
        why = f"Moderate change in {cat_name}. Consistent with typical spending variation."

    return what, why


def _confidence_level(months_of_data: int, pct_change: float) -> str:
    if months_of_data >= _HIGH_CONF_MONTHS and abs(pct_change) >= _SIGNIFICANT_CHANGE_PCT:
        return "high"
    if months_of_data >= _MED_CONF_MONTHS:
        return "medium"
    return "low"


# ── Public API ────────────────────────────────────────────────────────────────

def get_spending_insights(
    uid: int,
    months: int = 3,
    anchor: date | None = None,
) -> dict[str, Any]:
    """
    Generate explainable spending insights for the last *months* months.

    Returns:
        insights           — list of month-over-month insight objects
        top_changes        — top 3 largest changes across all periods
        overall_trend      — 'increasing' | 'decreasing' | 'stable'
        trend_confidence   — confidence in the overall trend
        period_summaries   — per-month income/expense/net
        generated_at       — ISO timestamp
    """
    from datetime import datetime

    if anchor is None:
        anchor = date.today()
    months = max(2, min(months, 12))  # need at least 2 months for comparison

    # Gather per-month totals
    monthly_totals: list[dict] = []
    for y, m in reversed(list(_iter_months_back(anchor, months))):
        inc, exp = _month_totals(uid, y, m)
        monthly_totals.append({
            "year": y, "month": m,
            "label": f"{y:04d}-{m:02d}",
            "income": inc, "expenses": exp,
            "net": round(inc - exp, 2),
        })

    # Build historical category data for the whole window (for volatility)
    all_cat_history: dict[int | None, list[float]] = {}
    for entry in monthly_totals:
        cats = _month_expense_by_category(uid, entry["year"], entry["month"])
        for cat_id, amount in cats.items():
            all_cat_history.setdefault(cat_id, []).append(amount)

    insights: list[dict] = []
    all_changes: list[dict] = []

    # Compare consecutive months
    for i in range(1, len(monthly_totals)):
        prev_m = monthly_totals[i - 1]
        curr_m = monthly_totals[i]

        prev_cats = _month_expense_by_category(uid, prev_m["year"], prev_m["month"])
        curr_cats = _month_expense_by_category(uid, curr_m["year"], curr_m["month"])

        all_cat_ids = set(prev_cats) | set(curr_cats)
        period_changes: list[dict] = []

        for cat_id in all_cat_ids:
            prev_val = prev_cats.get(cat_id, 0.0)
            curr_val = curr_cats.get(cat_id, 0.0)
            delta = curr_val - prev_val

            if abs(delta) < _MIN_ABSOLUTE_CHANGE:
                continue

            pct = ((curr_val - prev_val) / prev_val * 100) if prev_val > 0 else (100.0 if curr_val > 0 else 0.0)
            if abs(pct) < _SIGNIFICANT_CHANGE_PCT and abs(delta) < _MIN_ABSOLUTE_CHANGE * 2:
                continue

            history = all_cat_history.get(cat_id, [])
            cat_name = _category_name(cat_id)
            what, why = _explain_change(cat_name, prev_val, curr_val, pct, history)
            confidence = _confidence_level(len(history), pct)

            change = {
                "category_id": cat_id,
                "category_name": cat_name,
                "period": curr_m["label"],
                "previous_period": prev_m["label"],
                "previous_amount": round(prev_val, 2),
                "current_amount": round(curr_val, 2),
                "delta": round(delta, 2),
                "pct_change": round(pct, 1),
                "what_changed": what,
                "why_it_changed": why,
                "confidence": confidence,
            }
            period_changes.append(change)
            all_changes.append(change)

        # Total expense change for this period
        total_prev = prev_m["expenses"]
        total_curr = curr_m["expenses"]
        total_pct = ((total_curr - total_prev) / total_prev * 100) if total_prev > 0 else 0.0

        insights.append({
            "period": curr_m["label"],
            "previous_period": prev_m["label"],
            "total_expense_change": round(total_curr - total_prev, 2),
            "total_expense_pct_change": round(total_pct, 1),
            "category_changes": sorted(period_changes, key=lambda x: -abs(x["delta"])),
        })

    # Top 3 changes across all periods
    top_changes = sorted(all_changes, key=lambda x: -abs(x["delta"]))[:3]

    # Overall trend
    if len(monthly_totals) >= 2:
        expense_series = [m["expenses"] for m in monthly_totals]
        first_half_avg = statistics.mean(expense_series[:len(expense_series)//2]) if expense_series else 0
        second_half_avg = statistics.mean(expense_series[len(expense_series)//2:]) if expense_series else 0
        if second_half_avg > first_half_avg * 1.05:
            overall_trend = "increasing"
        elif second_half_avg < first_half_avg * 0.95:
            overall_trend = "decreasing"
        else:
            overall_trend = "stable"
        trend_confidence = "high" if len(monthly_totals) >= 4 else "medium"
    else:
        overall_trend = "insufficient_data"
        trend_confidence = "low"

    logger.info(
        "Spending insights uid=%s months=%d insights=%d trend=%s",
        uid, months, len(all_changes), overall_trend,
    )

    return {
        "insights": insights,
        "top_changes": top_changes,
        "overall_trend": overall_trend,
        "trend_confidence": trend_confidence,
        "period_summaries": monthly_totals,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
