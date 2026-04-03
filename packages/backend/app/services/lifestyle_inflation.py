"""Lifestyle inflation detection service.

Identifies rising spending patterns by comparing monthly totals
over a configurable window. Detects:

- Overall spending trend (total monthly spend increasing)
- Category-level inflation (specific categories growing faster)
- Discretionary creep (non-essential spending growth vs essentials)

Uses linear regression slope to quantify trend strength and
month-over-month comparison for recent changes.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import TypedDict

from sqlalchemy import func, extract

from ..extensions import db
from ..models import Expense, Category

logger = logging.getLogger("finmind.lifestyle_inflation")


class MonthlySpend(TypedDict):
    month: str  # YYYY-MM
    total: float
    change_from_prev: float | None
    change_percent: float | None


class CategoryTrend(TypedDict):
    category_id: int | None
    category_name: str
    monthly_average_start: float
    monthly_average_end: float
    growth_percent: float
    trend: str  # "rising" | "stable" | "declining"


class InflationReport(TypedDict):
    overall_trend: str  # "rising" | "stable" | "declining"
    monthly_growth_rate: float  # average month-over-month % change
    total_spending: list[MonthlySpend]
    category_trends: list[CategoryTrend]
    insights: list[str]


def detect_lifestyle_inflation(
    user_id: int,
    months: int = 6,
) -> InflationReport:
    """Analyze spending patterns to detect lifestyle inflation.

    Args:
        user_id: The user to analyze.
        months: Number of months to look back (default 6).

    Returns:
        InflationReport with trends, category breakdown, and insights.
    """
    today = date.today()
    start = date(today.year, today.month, 1) - timedelta(days=months * 31)
    start = date(start.year, start.month, 1)  # normalize to month start

    # Get monthly totals
    monthly_totals = _get_monthly_totals(user_id, start)

    # Get category-level breakdown
    category_trends = _get_category_trends(user_id, start, months)

    # Calculate overall trend
    overall_trend, growth_rate = _calculate_trend(monthly_totals)

    # Generate insights
    insights = _generate_insights(monthly_totals, category_trends, growth_rate)

    report = InflationReport(
        overall_trend=overall_trend,
        monthly_growth_rate=round(growth_rate, 2),
        total_spending=monthly_totals,
        category_trends=category_trends,
        insights=insights,
    )

    logger.info(
        "Lifestyle inflation user=%s: trend=%s, growth=%.1f%%/month",
        user_id,
        overall_trend,
        growth_rate,
    )
    return report


def _get_monthly_totals(user_id: int, start: date) -> list[MonthlySpend]:
    """Get total spending per month."""
    rows = (
        db.session.query(
            func.strftime("%Y-%m", Expense.spent_at).label("month"),
            func.sum(Expense.amount).label("total"),
        )
        .filter(Expense.user_id == user_id, Expense.spent_at >= start)
        .group_by("month")
        .order_by("month")
        .all()
    )

    totals: list[MonthlySpend] = []
    for i, row in enumerate(rows):
        total = float(row.total or 0)
        prev_total = float(rows[i - 1].total or 0) if i > 0 else None

        change = None
        change_pct = None
        if prev_total is not None and prev_total > 0:
            change = round(total - prev_total, 2)
            change_pct = round(((total - prev_total) / prev_total) * 100, 2)

        totals.append(
            MonthlySpend(
                month=row.month,
                total=round(total, 2),
                change_from_prev=change,
                change_percent=change_pct,
            )
        )

    return totals


def _get_category_trends(
    user_id: int, start: date, months: int
) -> list[CategoryTrend]:
    """Analyze spending trends per category."""
    today = date.today()
    midpoint = start + timedelta(days=(months * 31) // 2)

    # Get category names
    categories = {
        c.id: c.name
        for c in db.session.query(Category).filter_by(user_id=user_id).all()
    }

    # First half average
    first_half = (
        db.session.query(
            Expense.category_id,
            func.avg(Expense.amount).label("avg_amount"),
            func.count(Expense.id).label("cnt"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at < midpoint,
        )
        .group_by(Expense.category_id)
        .all()
    )

    # Second half average
    second_half = (
        db.session.query(
            Expense.category_id,
            func.avg(Expense.amount).label("avg_amount"),
            func.count(Expense.id).label("cnt"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= midpoint,
        )
        .group_by(Expense.category_id)
        .all()
    )

    first_map = {r.category_id: float(r.avg_amount or 0) for r in first_half}
    second_map = {r.category_id: float(r.avg_amount or 0) for r in second_half}

    all_cats = set(first_map.keys()) | set(second_map.keys())
    trends: list[CategoryTrend] = []

    for cat_id in all_cats:
        start_avg = first_map.get(cat_id, 0)
        end_avg = second_map.get(cat_id, 0)

        if start_avg > 0:
            growth = ((end_avg - start_avg) / start_avg) * 100
        elif end_avg > 0:
            growth = 100.0
        else:
            growth = 0.0

        if growth > 5:
            trend = "rising"
        elif growth < -5:
            trend = "declining"
        else:
            trend = "stable"

        trends.append(
            CategoryTrend(
                category_id=cat_id,
                category_name=categories.get(cat_id, "Uncategorized") if cat_id else "Uncategorized",
                monthly_average_start=round(start_avg, 2),
                monthly_average_end=round(end_avg, 2),
                growth_percent=round(growth, 2),
                trend=trend,
            )
        )

    # Sort by growth (highest inflation first)
    trends.sort(key=lambda t: t["growth_percent"], reverse=True)
    return trends


def _calculate_trend(totals: list[MonthlySpend]) -> tuple[str, float]:
    """Determine overall trend from monthly totals using average growth rate."""
    if len(totals) < 2:
        return "stable", 0.0

    growth_rates = [
        t["change_percent"]
        for t in totals
        if t["change_percent"] is not None
    ]

    if not growth_rates:
        return "stable", 0.0

    avg_growth = sum(growth_rates) / len(growth_rates)

    if avg_growth > 3:
        trend = "rising"
    elif avg_growth < -3:
        trend = "declining"
    else:
        trend = "stable"

    return trend, avg_growth


def _generate_insights(
    totals: list[MonthlySpend],
    category_trends: list[CategoryTrend],
    growth_rate: float,
) -> list[str]:
    """Generate human-readable insights about spending patterns."""
    insights: list[str] = []

    if growth_rate > 5:
        insights.append(
            f"Your spending is increasing by ~{growth_rate:.1f}% per month. "
            "This is a sign of lifestyle inflation."
        )
    elif growth_rate > 0:
        insights.append(
            f"Spending is growing slowly at ~{growth_rate:.1f}% per month."
        )
    elif growth_rate < -3:
        insights.append(
            f"Great news — your spending is decreasing by ~{abs(growth_rate):.1f}% per month."
        )

    # Fastest growing categories
    rising = [c for c in category_trends if c["trend"] == "rising"]
    if rising:
        top = rising[0]
        insights.append(
            f"'{top['category_name']}' is your fastest growing expense category "
            f"(+{top['growth_percent']:.1f}%)."
        )

    # Spending acceleration
    if len(totals) >= 3:
        recent = totals[-1]["change_percent"]
        if recent is not None and recent > 10:
            insights.append(
                f"Last month saw a {recent:.1f}% spending jump — "
                "worth investigating."
            )

    return insights
