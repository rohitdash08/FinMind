"""
Dynamic Budget Suggestions (Issue #73).

Suggests personalized budget limits for each spending category based on
3–6 months of actual spending history.  Uses the 50/30/20 rule as a
high-level guardrail and a statistical per-category model for specifics.

Algorithm per category
----------------------
1. Collect monthly totals for the last N months (3-6)
2. Remove outlier months (> mean + 1.5σ) to get a "clean" baseline
3. Suggested limit = clean baseline mean × (1 + breathing_room)
   where breathing_room = -0.10 (10% reduction) by default — nudges users
   to spend slightly less than their current average
4. Confidence:
   - "high"   — ≥4 months of data, low variance (CV < 0.3)
   - "medium" — ≥3 months OR moderate variance
   - "low"    — < 3 months OR high variance

Public API
----------
get_budget_suggestions(uid, months, reduction_pct) → SuggestionsResult dict
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.budget_suggestions")

# ── Constants ─────────────────────────────────────────────────────────────────

_DEFAULT_REDUCTION_PCT = 10.0    # suggest 10% below current average
_OUTLIER_SIGMA         = 1.5
_HIGH_CONF_MONTHS      = 4
_HIGH_CONF_CV          = 0.30    # coefficient of variation threshold
_50_30_20_NEEDS_PCT    = 0.50
_50_30_20_WANTS_PCT    = 0.30
_50_30_20_SAVINGS_PCT  = 0.20

# ── Helpers ───────────────────────────────────────────────────────────────────

def _iter_months_back(anchor: date, n: int):
    y, m = anchor.year, anchor.month
    for _ in range(n):
        yield y, m
        m -= 1
        if m == 0:
            m = 12
            y -= 1


def _monthly_category_spend(uid: int, year: int, month: int) -> dict[int | None, float]:
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


def _monthly_income(uid: int, year: int, month: int) -> float:
    return float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar() or 0
    )


def _category_name(cat_id: int | None) -> str:
    if cat_id is None:
        return "Uncategorized"
    cat = db.session.get(Category, cat_id)
    return cat.name if cat else f"Category {cat_id}"


def _remove_outliers(values: list[float]) -> list[float]:
    if len(values) < 3:
        return values
    mu  = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0
    if std == 0:
        return values
    return [v for v in values if v <= mu + _OUTLIER_SIGMA * std]


def _confidence(n_months: int, cv: float) -> str:
    if n_months >= _HIGH_CONF_MONTHS and cv < _HIGH_CONF_CV:
        return "high"
    if n_months >= 3:
        return "medium"
    return "low"


def _confidence_score(conf: str) -> float:
    return {"high": 0.9, "medium": 0.7, "low": 0.4}.get(conf, 0.4)


# ── Public API ────────────────────────────────────────────────────────────────

def get_budget_suggestions(
    uid: int,
    months: int = 3,
    reduction_pct: float = _DEFAULT_REDUCTION_PCT,
    anchor: date | None = None,
) -> dict[str, Any]:
    """
    Suggest personalized monthly budget limits per spending category.

    Parameters
    ----------
    uid           : authenticated user id
    months        : look-back window (3–6 per spec)
    reduction_pct : how much below current average to set the suggestion
                    (e.g. 10 → suggest 10% less than average). Use 0 for
                    a "maintain current" suggestion.
    anchor        : end month for the analysis (defaults to today)

    Returns
    -------
    dict with:
        suggestions      — per-category budget suggestions
        total_suggested  — sum of all suggested limits
        income_summary   — avg income + 50/30/20 targets
        overall_confidence — weighted average confidence
        data_months_used — effective months analysed
        generated_at
    """
    from datetime import datetime

    if anchor is None:
        anchor = date.today()
    months = max(3, min(months, 6))
    reduction_factor = 1.0 - (reduction_pct / 100.0)

    # Collect per-category monthly data
    cat_monthly: dict[int | None, list[float]] = defaultdict(list)
    income_monthly: list[float] = []

    for y, m in _iter_months_back(anchor, months):
        cat_spend = _monthly_category_spend(uid, y, m)
        inc = _monthly_income(uid, y, m)
        income_monthly.append(inc)
        for cat_id, amount in cat_spend.items():
            if amount > 0:
                cat_monthly[cat_id].append(amount)

    months_with_data = sum(1 for inc in income_monthly if inc > 0)
    avg_income = round(statistics.mean(income_monthly), 2) if income_monthly else 0.0

    suggestions: list[dict] = []
    total_suggested = 0.0
    confidence_scores: list[float] = []

    for cat_id, values in cat_monthly.items():
        clean = _remove_outliers(values)
        if not clean:
            clean = values

        mean_spend  = statistics.mean(clean)
        std_spend   = statistics.stdev(clean) if len(clean) > 1 else 0.0
        cv          = std_spend / mean_spend if mean_spend > 0 else 0.0

        suggested   = round(mean_spend * reduction_factor, 2)
        conf        = _confidence(len(values), cv)
        score       = _confidence_score(conf)
        confidence_scores.append(score)

        suggestions.append({
            "category_id":        cat_id,
            "category_name":      _category_name(cat_id),
            "current_avg_spend":  round(mean_spend, 2),
            "suggested_limit":    suggested,
            "saving_opportunity": round(mean_spend - suggested, 2),
            "std_deviation":      round(std_spend, 2),
            "confidence":         conf,
            "confidence_score":   score,
            "data_points":        len(values),
            "rationale": (
                f"Based on {len(values)} months of data. "
                f"Average spend: {mean_spend:.2f}. "
                f"Suggested limit is {reduction_pct:.0f}% below average "
                f"(confidence: {conf})."
            ),
        })
        total_suggested += suggested

    # Sort by saving_opportunity descending
    suggestions.sort(key=lambda x: -x["saving_opportunity"])

    overall_conf = (
        round(statistics.mean(confidence_scores), 2) if confidence_scores else 0.4
    )

    # 50/30/20 targets based on avg income
    income_targets = {}
    if avg_income > 0:
        income_targets = {
            "needs_target":   round(avg_income * _50_30_20_NEEDS_PCT, 2),
            "wants_target":   round(avg_income * _50_30_20_WANTS_PCT, 2),
            "savings_target": round(avg_income * _50_30_20_SAVINGS_PCT, 2),
            "total_budget":   round(avg_income * (1 - _50_30_20_SAVINGS_PCT), 2),
        }

    logger.info(
        "Budget suggestions uid=%s months=%d categories=%d avg_income=%.2f",
        uid, months, len(suggestions), avg_income,
    )

    return {
        "suggestions":         suggestions,
        "total_suggested":     round(total_suggested, 2),
        "income_summary": {
            "avg_monthly_income": avg_income,
            **income_targets,
        },
        "overall_confidence":  overall_conf,
        "data_months_used":    months_with_data,
        "generated_at":        datetime.utcnow().isoformat() + "Z",
    }
