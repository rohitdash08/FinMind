"""Smart digest service — weekly financial summary with trends and insights."""

from datetime import datetime, timedelta
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, WeeklyDigest

import logging

logger = logging.getLogger("finmind.digest")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _period_bounds(period="weekly", reference_date=None):
    """Return (start, end) for the requested period.

    Weekly periods start on Monday.  Monthly periods start on the 1st.
    """
    ref = reference_date or datetime.utcnow().date()
    if period == "weekly":
        start = ref - timedelta(days=ref.weekday())
        end = start + timedelta(days=6)
    elif period == "monthly":
        start = ref.replace(day=1)
        if ref.month == 12:
            end = ref.replace(year=ref.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = ref.replace(month=ref.month + 1, day=1) - timedelta(days=1)
    else:
        raise ValueError(f"Unknown period: {period}")
    return start, end


def _category_breakdown(query_result):
    """Convert raw query rows into {category: total} dict."""
    breakdown = {}
    for cat, total in query_result:
        if cat:
            breakdown[cat] = float(total)
    return breakdown


def _detect_trends(current, previous):
    """Compare two breakdown dicts and return trend list."""
    trends = []
    all_cats = set(current) | set(previous)
    for cat in sorted(all_cats):
        cur = current.get(cat, 0)
        prev = previous.get(cat, 0)
        if prev == 0:
            if cur > 0:
                change_pct = 100.0
                direction = "new"
            else:
                continue
        else:
            change_pct = round(((cur - prev) / prev) * 100, 1)
            direction = "up" if change_pct > 0 else "down"

        if abs(change_pct) >= 15:
            trends.append(
                {
                    "category": cat,
                    "current": cur,
                    "previous": prev,
                    "change_pct": change_pct,
                    "direction": direction,
                }
            )
    return trends


def _generate_insights(total_current, total_previous, breakdown, trends):
    """Produce human-readable insight strings."""
    insights = []

    # Top spending category
    if breakdown:
        top_cat = max(breakdown, key=breakdown.get)
        top_amount = breakdown[top_cat]
        if total_current > 0:
            pct = round((top_amount / total_current) * 100, 1)
            insights.append(f"Top category: {top_cat} ({pct}% of total spending)")

    # Significant changes
    for t in trends:
        if t["direction"] == "up":
            insights.append(
                f"{t['category']} spending up {abs(t['change_pct'])}% "
                f"({t['previous']:.0f} -> {t['current']:.0f})"
            )
        elif t["direction"] == "down":
            insights.append(
                f"{t['category']} spending down {abs(t['change_pct'])}% "
                f"({t['previous']:.0f} -> {t['current']:.0f})"
            )
        elif t["direction"] == "new":
            insights.append(f"New spending in {t['category']} ({t['current']:.0f})")

    # Overall comparison
    if total_previous > 0:
        overall_change = round(
            ((total_current - total_previous) / total_previous) * 100, 1
        )
        if overall_change > 10:
            insights.append(f"Overall spending up {overall_change}% from last period")
        elif overall_change < -10:
            insights.append(
                f"Overall spending down {abs(overall_change)}% from last period"
            )

    if not insights:
        insights.append("Spending patterns are stable this period.")

    return insights


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_digest(user_id, period="weekly", reference_date=None):
    """Generate a financial digest for the given period.

    Returns a dict with total, breakdown, trends, and insights.
    Creates/updates a WeeklyDigest record.
    """
    start, end = _period_bounds(period, reference_date)

    # --- Current period ---
    current_rows = (
        db.session.query(Expense.category, func.sum(Expense.amount))
        .filter(
            Expense.user_id == user_id,
            Expense.date >= start,
            Expense.date <= end,
        )
        .group_by(Expense.category)
        .all()
    )
    current_breakdown = _category_breakdown(current_rows)
    total_current = sum(current_breakdown.values())

    # --- Previous period ---
    period_days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_days - 1)

    previous_rows = (
        db.session.query(Expense.category, func.sum(Expense.amount))
        .filter(
            Expense.user_id == user_id,
            Expense.date >= prev_start,
            Expense.date <= prev_end,
        )
        .group_by(Expense.category)
        .all()
    )
    previous_breakdown = _category_breakdown(previous_rows)
    total_previous = sum(previous_breakdown.values())

    # --- Trends & insights ---
    trends = _detect_trends(current_breakdown, previous_breakdown)
    insights = _generate_insights(
        total_current, total_previous, current_breakdown, trends
    )

    digest_data = {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "period_type": period,
        "total_spent": total_current,
        "total_previous": total_previous,
        "category_breakdown": current_breakdown,
        "trends": trends,
        "insights": insights,
    }

    # Upsert digest record
    existing = WeeklyDigest.query.filter_by(
        user_id=user_id,
        period_start=start,
        period_end=end,
    ).first()

    if existing:
        existing.total_spent = total_current
        existing.category_breakdown = current_breakdown
        existing.trends = trends
        existing.insights = insights
        existing.generated_at = datetime.utcnow()
    else:
        existing = WeeklyDigest(
            user_id=user_id,
            period_start=start,
            period_end=end,
            period_type=period,
            total_spent=total_current,
            category_breakdown=current_breakdown,
            trends=trends,
            insights=insights,
            generated_at=datetime.utcnow(),
        )
        db.session.add(existing)

    db.session.commit()
    digest_data["id"] = existing.id
    return digest_data


def get_digest_history(user_id, limit=10, period=None):
    """Return historical digests for a user."""
    q = WeeklyDigest.query.filter_by(user_id=user_id)
    if period:
        q = q.filter_by(period_type=period)
    q = q.order_by(WeeklyDigest.period_start.desc())
    if limit:
        q = q.limit(limit)
    digests = q.all()
    return [
        {
            "id": d.id,
            "period_start": d.period_start.isoformat(),
            "period_end": d.period_end.isoformat(),
            "period_type": d.period_type,
            "total_spent": d.total_spent,
            "category_breakdown": d.category_breakdown,
            "trends": d.trends,
            "insights": d.insights,
            "generated_at": d.generated_at.isoformat(),
        }
        for d in digests
    ]
