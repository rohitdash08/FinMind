"""
Dynamic Budget Suggestions — FinMind (#73)

Suggests monthly budget limits per category using 3-6 months of
historical spending data. Includes a confidence score based on
data completeness.
"""
from __future__ import annotations

import logging
import math
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import func, extract

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.budget_suggestions")

# ── Configuration ──────────────────────────────────────────────────────────────
MIN_MONTHS = 3         # minimum months of data to generate a suggestion
MAX_MONTHS = 6         # maximum months used for baseline
BUFFER_RATIO = 1.10    # suggested budget = avg * 1.10 (10% buffer)
STDDEV_BUFFER = 0.5    # suggested budget += 0.5 * stddev for variance


class BudgetSuggestion(TypedDict):
    category_id: int | None
    category_name: str
    avg_monthly_spend: float
    stddev_monthly_spend: float
    suggested_budget: float
    confidence_score: float      # 0.0 - 1.0 based on months of data
    months_of_data: int
    rationale: str


class BudgetSuggestionsResult(TypedDict):
    reference_months: list[str]
    suggestions_count: int
    suggestions: list[BudgetSuggestion]


# ── Internal helpers ───────────────────────────────────────────────────────────

def _prior_months(anchor_ym: str, n: int) -> list[str]:
    """Return the n months preceding anchor_ym (oldest first)."""
    year, month = int(anchor_ym[:4]), int(anchor_ym[5:7])
    result: list[str] = []
    for _ in range(n):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        result.append(f"{year:04d}-{month:02d}")
    return list(reversed(result))  # oldest first


def _category_monthly_spend(uid: int, months: list[str]) -> dict[int, dict]:
    """Return per-category monthly totals across the given month list.

    Returns {
      category_id: {
        "name": str,
        "monthly": {ym: Decimal}   # only months with data
      }
    }
    """
    categories: dict[int, dict] = {}
    for ym in months:
        year, month = int(ym[:4]), int(ym[5:7])
        rows = (
            db.session.query(
                Expense.category_id,
                Category.name,
                func.sum(Expense.amount).label("total"),
            )
            .outerjoin(Category, Category.id == Expense.category_id)
            .filter(
                Expense.user_id == uid,
                Expense.expense_type == "EXPENSE",
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
            )
            .group_by(Expense.category_id, Category.name)
            .all()
        )
        for row in rows:
            if row.category_id not in categories:
                categories[row.category_id] = {
                    "name": row.name or "Uncategorized",
                    "monthly": {},
                }
            categories[row.category_id]["monthly"][ym] = Decimal(str(row.total))
    return categories


def _compute_suggestion(cat_info: dict, months: list[str]) -> tuple[float, float, float, float, int]:
    """Return (avg, stddev, suggested_budget, confidence, months_of_data)."""
    monthly = cat_info["monthly"]
    # Fill zero for months with no data
    values = [float(monthly.get(ym, Decimal("0"))) for ym in months]
    # Count non-zero months
    non_zero = [v for v in values if v > 0]
    months_of_data = len(non_zero)

    if months_of_data == 0:
        return 0.0, 0.0, 0.0, 0.0, 0

    n = len(non_zero)
    avg = sum(non_zero) / n
    if n == 1:
        stddev = avg * 0.2  # conservative estimate for single data point
    else:
        variance = sum((x - avg) ** 2 for x in non_zero) / (n - 1)
        stddev = math.sqrt(variance)

    # Suggested budget: avg * buffer + partial stddev
    suggested = avg * BUFFER_RATIO + stddev * STDDEV_BUFFER
    # Round up to nearest 100 for cleanliness
    suggested = math.ceil(suggested / 100) * 100 if suggested > 100 else math.ceil(suggested / 10) * 10

    # Confidence: based on months of data vs MAX_MONTHS
    # Full confidence (1.0) requires MAX_MONTHS data points
    confidence = min(months_of_data / MAX_MONTHS, 1.0)

    return round(avg, 2), round(stddev, 2), round(float(suggested), 2), round(confidence, 2), months_of_data


def _rationale(avg: float, stddev: float, confidence: float, months: int) -> str:
    """Generate a human-readable rationale for the suggestion."""
    cv = stddev / avg if avg > 0 else 0  # coefficient of variation
    if confidence < 0.5:
        stability = "limited data"
    elif cv < 0.15:
        stability = "highly consistent"
    elif cv < 0.35:
        stability = "moderately variable"
    else:
        stability = "highly variable"

    conf_pct = int(confidence * 100)
    return (
        f"Based on {months} month(s) of data ({stability} spending). "
        f"Average: {avg:.0f}, variance buffer applied. "
        f"Confidence: {conf_pct}%."
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def get_budget_suggestions(uid: int, anchor_ym: str) -> BudgetSuggestionsResult:
    """Generate dynamic budget suggestions for user *uid*.

    Uses up to MAX_MONTHS (6) months of data prior to *anchor_ym* (YYYY-MM).
    Only suggests budgets for categories with at least MIN_MONTHS data points.

    Returns BudgetSuggestionsResult with sorted list of suggestions (highest
    avg spend first) and confidence scores.
    """
    reference_months = _prior_months(anchor_ym, MAX_MONTHS)
    category_data = _category_monthly_spend(uid, reference_months)

    suggestions: list[BudgetSuggestion] = []

    for cat_id, cat_info in category_data.items():
        avg, stddev, suggested, confidence, months_of_data = _compute_suggestion(
            cat_info, reference_months
        )
        if months_of_data < MIN_MONTHS:
            # Not enough data for a reliable suggestion
            continue
        if avg <= 0:
            continue

        suggestions.append(BudgetSuggestion(
            category_id=cat_id,
            category_name=cat_info["name"],
            avg_monthly_spend=avg,
            stddev_monthly_spend=stddev,
            suggested_budget=suggested,
            confidence_score=confidence,
            months_of_data=months_of_data,
            rationale=_rationale(avg, stddev, confidence, months_of_data),
        ))

    # Sort by avg_monthly_spend descending (highest spend categories first)
    suggestions.sort(key=lambda s: -s["avg_monthly_spend"])

    logger.info(
        "budget_suggestions uid=%d anchor=%s months=%d suggestions=%d",
        uid, anchor_ym, len(reference_months), len(suggestions),
    )

    return BudgetSuggestionsResult(
        reference_months=reference_months,
        suggestions_count=len(suggestions),
        suggestions=suggestions,
    )