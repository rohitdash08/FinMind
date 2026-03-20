from __future__ import annotations

import statistics
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func

from app.models import Transaction
from app import db


# ---------------------------------------------------------------------------
# Keywords that indicate lifestyle (non-essential) spending
# ---------------------------------------------------------------------------

LIFESTYLE_KEYWORDS = {
    "dining", "restaurant", "coffee", "cafe", "bar", "pub", "takeaway",
    "gym", "fitness", "yoga", "spa", "beauty", "salon", "barber",
    "entertainment", "cinema", "theater", "concert", "streaming", "netflix",
    "spotify", "subscription", "clothing", "fashion", "shopping", "amazon",
    "travel", "hotel", "airbnb", "vacation", "holiday", "trip",
    "gaming", "apps", "accessories", "gadgets", "electronics",
}


def _is_lifestyle(category: str) -> bool:
    cat_lower = (category or "").lower()
    return any(kw in cat_lower for kw in LIFESTYLE_KEYWORDS)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class InflationSignal:
    category: str
    is_lifestyle: bool
    monthly_avg_old: float    # avg of earlier half of the period
    monthly_avg_new: float    # avg of recent half
    inflation_pct: float      # % increase
    severity: str             # "mild" (5-20%), "moderate" (20-50%), "high" (>50%)
    trend_note: str


@dataclass
class LifestyleInflationResult:
    analysis_months: int
    total_lifestyle_old: float
    total_lifestyle_new: float
    lifestyle_inflation_pct: float
    inflation_signals: list[InflationSignal]
    top_inflated_category: Optional[str]
    summary: str
    is_inflating: bool


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

def get_lifestyle_inflation(
    user_id: int,
    months: int = 6,
    threshold_pct: float = 5.0,
) -> LifestyleInflationResult:
    """
    Detect rising lifestyle expenses over time by comparing the older half
    of the analysis period to the recent half.

    Args:
        user_id: JWT user id
        months: total months to analyze (2-24, must be even for fair comparison)
        threshold_pct: minimum % increase to flag as inflation (default 5%)
    """
    months = max(2, min(24, months))
    if months % 2 != 0:
        months += 1  # ensure even split

    cutoff = date.today() - timedelta(days=months * 31)

    rows = (
        db.session.query(
            func.strftime("%Y-%m", Transaction.date).label("month"),
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.date >= cutoff,
            Transaction.type == "expense",
        )
        .group_by("month", Transaction.category)
        .all()
    )

    if not rows:
        return LifestyleInflationResult(
            analysis_months=months,
            total_lifestyle_old=0.0,
            total_lifestyle_new=0.0,
            lifestyle_inflation_pct=0.0,
            inflation_signals=[],
            top_inflated_category=None,
            summary="No spending data available for lifestyle inflation analysis.",
            is_inflating=False,
        )

    # Build {month -> {category -> amount}} map
    all_months_set: set[str] = set()
    data: dict[str, dict[str, float]] = {}
    for row in rows:
        m = row.month
        cat = row.category or "Uncategorized"
        all_months_set.add(m)
        if cat not in data:
            data[cat] = {}
        data[cat][m] = float(row.total or 0)

    sorted_months = sorted(all_months_set)
    half = len(sorted_months) // 2
    old_months = sorted_months[:half]
    new_months = sorted_months[half:]

    if not old_months or not new_months:
        return LifestyleInflationResult(
            analysis_months=months,
            total_lifestyle_old=0.0,
            total_lifestyle_new=0.0,
            lifestyle_inflation_pct=0.0,
            inflation_signals=[],
            top_inflated_category=None,
            summary="Insufficient data to compare periods.",
            is_inflating=False,
        )

    signals: list[InflationSignal] = []
    total_ls_old = 0.0
    total_ls_new = 0.0

    for cat, month_map in data.items():
        old_vals = [month_map.get(m, 0.0) for m in old_months]
        new_vals = [month_map.get(m, 0.0) for m in new_months]

        avg_old = statistics.mean(old_vals)
        avg_new = statistics.mean(new_vals)

        is_ls = _is_lifestyle(cat)
        if is_ls:
            total_ls_old += avg_old
            total_ls_new += avg_new

        if avg_old <= 0:
            continue

        inflation_pct = round((avg_new - avg_old) / avg_old * 100, 1)

        if inflation_pct < threshold_pct:
            continue  # not inflating enough to flag

        # Severity
        if inflation_pct >= 50:
            severity = "high"
        elif inflation_pct >= 20:
            severity = "moderate"
        else:
            severity = "mild"

        ls_label = "lifestyle" if is_ls else "general"
        note = (
            f"{cat} ({ls_label}) avg {inflation_pct:+.1f}% over period "
            f"(${avg_old:.2f} -> ${avg_new:.2f}/month)."
        )
        signals.append(
            InflationSignal(
                category=cat,
                is_lifestyle=is_ls,
                monthly_avg_old=round(avg_old, 2),
                monthly_avg_new=round(avg_new, 2),
                inflation_pct=inflation_pct,
                severity=severity,
                trend_note=note,
            )
        )

    # Sort by inflation % descending
    signals.sort(key=lambda s: -s.inflation_pct)

    total_ls_old = round(total_ls_old, 2)
    total_ls_new = round(total_ls_new, 2)

    if total_ls_old > 0:
        lifestyle_inflation_pct = round((total_ls_new - total_ls_old) / total_ls_old * 100, 1)
    else:
        lifestyle_inflation_pct = 0.0

    is_inflating = lifestyle_inflation_pct >= threshold_pct
    top_inflated = signals[0].category if signals else None

    if not signals:
        summary = "No significant lifestyle inflation detected. Spending patterns look stable."
    elif is_inflating:
        summary = (
            f"Lifestyle inflation detected: +{lifestyle_inflation_pct:.1f}% over the analysis period. "
            f"Top driver: {top_inflated}."
        )
    else:
        summary = (
            f"Some category increases found ({len(signals)}) but overall lifestyle spending "
            f"is relatively stable ({lifestyle_inflation_pct:+.1f}%)."
        )

    return LifestyleInflationResult(
        analysis_months=months,
        total_lifestyle_old=total_ls_old,
        total_lifestyle_new=total_ls_new,
        lifestyle_inflation_pct=lifestyle_inflation_pct,
        inflation_signals=signals,
        top_inflated_category=top_inflated,
        summary=summary,
        is_inflating=is_inflating,
    )