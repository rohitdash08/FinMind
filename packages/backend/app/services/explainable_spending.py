from __future__ import annotations

import statistics
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func

from app.models import Transaction
from app import db


@dataclass
class SpendingChange:
    category: str
    current_amount: float
    previous_amount: float
    change_amount: float      # positive = increase, negative = decrease
    change_pct: float         # e.g. 25.0 = 25% increase
    explanation: str
    confidence: float         # 0.0 - 1.0


@dataclass
class SpendingInsightsResult:
    period_current: str        # YYYY-MM
    period_previous: str       # YYYY-MM
    total_current: float
    total_previous: float
    total_change_pct: float
    insights: list[SpendingChange]
    summary: str
    confidence: float


def _get_category_totals(user_id: int, year: int, month: int) -> dict[str, float]:
    """Return {category: total_spend} for a given year-month."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    rows = (
        db.session.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.type == "expense",
        )
        .group_by(Transaction.category)
        .all()
    )
    return {(row.category or "Uncategorized"): float(row.total or 0) for row in rows}


def _explain_change(
    category: str,
    current: float,
    previous: float,
    change_pct: float,
) -> tuple[str, float]:
    """Generate human-readable explanation and a confidence score."""
    abs_pct = abs(change_pct)
    direction = "increased" if change_pct > 0 else "decreased"
    diff = abs(current - previous)

    if previous == 0:
        return (
            f"{category} spending appeared for the first time this month (${current:.2f}).",
            0.7,
        )

    if current == 0:
        return (
            f"{category} spending disappeared entirely this month (was ${previous:.2f}).",
            0.8,
        )

    # High confidence for large changes
    if abs_pct >= 50:
        confidence = 0.9
        note = "a significant shift"
    elif abs_pct >= 25:
        confidence = 0.75
        note = "a notable change"
    else:
        confidence = 0.6
        note = "a moderate change"

    explanation = (
        f"{category} spending {direction} by {abs_pct:.1f}% "
        f"(${previous:.2f} -> ${current:.2f}, {note} of ${diff:.2f})."
    )
    return explanation, confidence


def get_spending_insights(
    user_id: int,
    month: Optional[str] = None,
) -> SpendingInsightsResult:
    """
    Explain WHY spending changed compared to the previous month.

    Args:
        user_id: JWT user id
        month: YYYY-MM string; defaults to current month
    """
    today = date.today()

    if month:
        try:
            year, mon = int(month[:4]), int(month[5:7])
        except (ValueError, IndexError):
            year, mon = today.year, today.month
    else:
        year, mon = today.year, today.month

    # Previous month
    if mon == 1:
        prev_year, prev_mon = year - 1, 12
    else:
        prev_year, prev_mon = year, mon - 1

    current_totals = _get_category_totals(user_id, year, mon)
    previous_totals = _get_category_totals(user_id, prev_year, prev_mon)

    all_categories = set(current_totals) | set(previous_totals)

    if not all_categories:
        return SpendingInsightsResult(
            period_current=f"{year:04d}-{mon:02d}",
            period_previous=f"{prev_year:04d}-{prev_mon:02d}",
            total_current=0.0,
            total_previous=0.0,
            total_change_pct=0.0,
            insights=[],
            summary="No spending data found for the selected period.",
            confidence=0.0,
        )

    total_current = sum(current_totals.values())
    total_previous = sum(previous_totals.values())

    if total_previous > 0:
        total_change_pct = round((total_current - total_previous) / total_previous * 100, 1)
    else:
        total_change_pct = 0.0

    insights: list[SpendingChange] = []
    for cat in all_categories:
        cur = current_totals.get(cat, 0.0)
        prev = previous_totals.get(cat, 0.0)

        if prev > 0:
            change_pct = round((cur - prev) / prev * 100, 1)
        else:
            change_pct = 100.0 if cur > 0 else 0.0

        # Only surface changes >= 5% or > $10
        if abs(change_pct) < 5 and abs(cur - prev) <= 10:
            continue

        explanation, conf = _explain_change(cat, cur, prev, change_pct)
        insights.append(
            SpendingChange(
                category=cat,
                current_amount=round(cur, 2),
                previous_amount=round(prev, 2),
                change_amount=round(cur - prev, 2),
                change_pct=change_pct,
                explanation=explanation,
                confidence=conf,
            )
        )

    # Sort by absolute change amount descending
    insights.sort(key=lambda x: -abs(x.change_amount))

    # Overall confidence based on how many categories have data
    overall_confidence = round(
        statistics.mean([i.confidence for i in insights]) if insights else 0.0, 2
    )

    # Generate summary
    if not insights:
        summary = "Spending was consistent with the previous month across all categories."
    elif total_change_pct > 10:
        top = insights[0].category if insights else ""
        summary = (
            f"Total spending increased by {total_change_pct}% vs last month. "
            f"The biggest driver was {top}."
        )
    elif total_change_pct < -10:
        top = insights[0].category if insights else ""
        summary = (
            f"Total spending decreased by {abs(total_change_pct)}% vs last month. "
            f"{top} saw the largest reduction."
        )
    else:
        summary = (
            f"Spending changed by {total_change_pct}% vs last month "
            f"with {len(insights)} notable category shifts."
        )

    return SpendingInsightsResult(
        period_current=f"{year:04d}-{mon:02d}",
        period_previous=f"{prev_year:04d}-{prev_mon:02d}",
        total_current=round(total_current, 2),
        total_previous=round(total_previous, 2),
        total_change_pct=total_change_pct,
        insights=insights,
        summary=summary,
        confidence=overall_confidence,
    )