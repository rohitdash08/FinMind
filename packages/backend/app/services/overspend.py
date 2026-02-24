"""
overspend.py — Category overspend early warning service.

Checks the current month's spending against per-category budget limits
and returns structured warnings at 70% (WARNING) and 100% (EXCEEDED) thresholds.

Public API:
    check_category_warnings(uid, session, reference_date=None) -> list[dict]
    budget_to_dict(budget, category_name) -> dict
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from ..models import CategoryBudget, Category, Expense

logger = logging.getLogger("finmind.overspend")

WARNING_THRESHOLD = 0.70   # 70% → WARNING
EXCEEDED_THRESHOLD = 1.00  # 100% → EXCEEDED


def check_category_warnings(
    uid: int,
    session: Session,
    reference_date: date | None = None,
) -> list[dict]:
    """
    Return a list of overspend warnings for the current month.

    Each entry represents a category where the user has set a monthly_limit
    and spending has reached at least WARNING_THRESHOLD.

    Returns:
        [
          {
            "category_id": <int>,
            "category_name": <str>,
            "monthly_limit": <float>,
            "currency": <str>,
            "spent": <float>,
            "pct_used": <float>,      # 0.0–1.0+ (can exceed 1.0)
            "remaining": <float>,     # negative if exceeded
            "status": "WARNING" | "EXCEEDED",
            "month": "YYYY-MM",
          },
          ...
        ]
    """
    today = reference_date or date.today()
    year, month = today.year, today.month
    ym = f"{year}-{month:02d}"

    # Fetch all budgets for this user
    budgets = (
        session.query(CategoryBudget, Category.name)
        .join(Category, CategoryBudget.category_id == Category.id)
        .filter(CategoryBudget.user_id == uid)
        .all()
    )

    if not budgets:
        return []

    # Fetch this month's spend per category in one query
    rows = (
        session.query(
            Expense.category_id,
            Expense.currency,
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Expense.currency)
        .all()
    )

    # Build spend lookup: {(category_id, currency): total}
    spend_map: dict[tuple, Decimal] = {}
    for row in rows:
        key = (row.category_id, row.currency)
        spend_map[key] = spend_map.get(key, Decimal(0)) + Decimal(str(row.total))

    warnings = []
    for budget, cat_name in budgets:
        # Use budget currency to look up spend
        spent = float(spend_map.get((budget.category_id, budget.currency), Decimal(0)))
        limit = float(budget.monthly_limit)

        if limit <= 0:
            continue

        pct_used = spent / limit

        if pct_used < WARNING_THRESHOLD:
            continue

        status = "EXCEEDED" if pct_used >= EXCEEDED_THRESHOLD else "WARNING"

        warnings.append({
            "category_id": budget.category_id,
            "category_name": cat_name,
            "monthly_limit": limit,
            "currency": budget.currency,
            "spent": round(spent, 2),
            "pct_used": round(pct_used, 4),
            "remaining": round(limit - spent, 2),
            "status": status,
            "month": ym,
        })

    # Sort: EXCEEDED first, then by pct_used descending
    warnings.sort(key=lambda w: (-int(w["status"] == "EXCEEDED"), -w["pct_used"]))
    logger.info("Overspend check user=%s month=%s warnings=%d", uid, ym, len(warnings))
    return warnings


def budget_to_dict(budget: CategoryBudget, category_name: str = "") -> dict:
    """Serialise a CategoryBudget to a plain dict."""
    return {
        "id": budget.id,
        "category_id": budget.category_id,
        "category_name": category_name,
        "monthly_limit": float(budget.monthly_limit),
        "currency": budget.currency,
        "created_at": budget.created_at.isoformat(),
        "updated_at": budget.updated_at.isoformat(),
    }
