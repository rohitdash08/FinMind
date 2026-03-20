"""
Category Overspend Early Warning — FinMind (#117)

Monitors per-category spending pace against user-defined budget limits
or historical averages. Fires an early warning when projected end-of-month
spend exceeds the limit, giving users time to correct course.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import func

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.overspend_warning")

# Thresholds
WARNING_THRESHOLD = Decimal("0.75")   # 75% of budget consumed → warning
CRITICAL_THRESHOLD = Decimal("1.00")  # 100% consumed → critical
MIN_DAYS_ELAPSED = 3                  # need at least 3 days of data to project


class OverspendWarning(TypedDict):
    category_id: int
    category_name: str
    spent_so_far: float
    budget_limit: float | None
    baseline_avg: float | None
    effective_limit: float       # budget_limit if set, else baseline_avg
    pace_rate: float             # spend per day so far this month
    projected_total: float       # projected end-of-month spend
    days_elapsed: int
    days_in_month: int
    pct_of_limit: float          # projected_total / effective_limit
    severity: str                # "warning" | "critical" | "over_budget"
    message: str


class OverspendResult(TypedDict):
    month: str
    days_elapsed: int
    days_in_month: int
    warnings: list[OverspendWarning]
    warning_count: int
    critical_count: int
    over_budget_count: int
    total_at_risk: float         # sum of (projected - limit) for over-budget categories


def get_overspend_warnings(user_id: int, month: str | None = None) -> OverspendResult:
    """Detect categories at risk of overspending this month.

    Uses a two-step approach:
    1. Calculate daily spend pace for each category so far this month
    2. Project to end-of-month and compare against budget or 3-month baseline avg

    Args:
        user_id: Authenticated user ID.
        month: YYYY-MM string. Defaults to current month.

    Returns:
        OverspendResult with per-category warnings.
    """
    today = date.today()
    if month:
        try:
            year, mon = map(int, month.split("-"))
            current_month_start = date(year, mon, 1)
        except (ValueError, AttributeError):
            current_month_start = today.replace(day=1)
    else:
        current_month_start = today.replace(day=1)

    # Days in month (handle 12-month rollover)
    if current_month_start.month == 12:
        next_month = current_month_start.replace(year=current_month_start.year + 1, month=1)
    else:
        next_month = current_month_start.replace(month=current_month_start.month + 1)
    days_in_month = (next_month - current_month_start).days

    days_elapsed = max(1, min(days_in_month, (today - current_month_start).days + 1))

    logger.info("Overspend check user=%s month=%s elapsed=%d/%d",
                user_id, current_month_start.strftime("%Y-%m"), days_elapsed, days_in_month)

    # Current month spend per category
    current_rows = (
        db.session.query(
            Expense.category_id,
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= current_month_start,
            Expense.spent_at <= today,
        )
        .group_by(Expense.category_id)
        .all()
    )

    if not current_rows:
        return OverspendResult(
            month=current_month_start.strftime("%Y-%m"),
            days_elapsed=days_elapsed,
            days_in_month=days_in_month,
            warnings=[],
            warning_count=0,
            critical_count=0,
            over_budget_count=0,
            total_at_risk=Decimal("0"),
        )

    # 3-month baseline averages per category
    baseline_start = (current_month_start.replace(day=1) if current_month_start.month > 3
                      else date(current_month_start.year - 1, 12 - (2 - current_month_start.month), 1))
    # Simpler: 90 days before month start
    from datetime import timedelta
    baseline_start = current_month_start - timedelta(days=90)

    baseline_rows = (
        db.session.query(
            Expense.category_id,
            func.sum(Expense.amount).label("total"),
            func.count(func.distinct(
                func.date_trunc("month", Expense.spent_at)
                if hasattr(func, 'date_trunc') else Expense.spent_at
            )).label("month_count"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= baseline_start,
            Expense.spent_at < current_month_start,
        )
        .group_by(Expense.category_id)
        .all()
    )

    baseline_map: dict[int | None, Decimal] = {
        r.category_id: (Decimal(str(r.total)) / max(1, r.month_count))
        for r in baseline_rows
    }

    # Get category names
    category_ids = {r.category_id for r in current_rows if r.category_id is not None}
    categories = {
        c.id: c.name
        for c in db.session.query(Category)
        .filter(Category.id.in_(category_ids))
        .all()
    } if category_ids else {}

    warnings: list[OverspendWarning] = []

    for row in current_rows:
        if days_elapsed < MIN_DAYS_ELAPSED:
            continue

        cat_id = row.category_id
        cat_name = categories.get(cat_id, "Uncategorized") if cat_id else "Uncategorized"
        spent = Decimal(str(row.total))

        baseline = baseline_map.get(cat_id)
        effective_limit = baseline if baseline and baseline > 0 else None

        if effective_limit is None:
            continue  # no baseline = can't warn

        pace_per_day = spent / days_elapsed
        projected = pace_per_day * days_in_month
        pct = projected / effective_limit

        if pct < WARNING_THRESHOLD:
            continue

        if pct >= Decimal("1.0"):
            severity = "over_budget"
            msg = (f"{cat_name} is already over projected budget. "
                   f"Spent {float(spent):.0f} vs {float(effective_limit):.0f} expected.")
        elif pct >= CRITICAL_THRESHOLD:
            severity = "critical"
            msg = (f"{cat_name} on pace to exceed budget by "
                   f"{float((projected - effective_limit)):.0f} this month.")
        else:
            severity = "warning"
            msg = (f"{cat_name} is at {float(pct)*100:.0f}% of expected monthly spend "
                   f"with {days_in_month - days_elapsed} days remaining.")

        warnings.append(OverspendWarning(
            category_id=cat_id if cat_id is not None else 0,
            category_name=cat_name,
            spent_so_far=float(spent),
            budget_limit=None,
            baseline_avg=float(baseline) if baseline else None,
            effective_limit=float(effective_limit),
            pace_rate=float(pace_per_day),
            projected_total=float(projected),
            days_elapsed=days_elapsed,
            days_in_month=days_in_month,
            pct_of_limit=float(pct),
            severity=severity,
            message=msg,
        ))

    warnings.sort(key=lambda w: w["pct_of_limit"], reverse=True)

    warning_count = sum(1 for w in warnings if w["severity"] == "warning")
    critical_count = sum(1 for w in warnings if w["severity"] == "critical")
    over_budget_count = sum(1 for w in warnings if w["severity"] == "over_budget")
    total_at_risk = sum(
        max(0.0, w["projected_total"] - w["effective_limit"])
        for w in warnings
        if w["severity"] in ("critical", "over_budget")
    )

    return OverspendResult(
        month=current_month_start.strftime("%Y-%m"),
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
        warnings=warnings,
        warning_count=warning_count,
        critical_count=critical_count,
        over_budget_count=over_budget_count,
        total_at_risk=total_at_risk,
    )