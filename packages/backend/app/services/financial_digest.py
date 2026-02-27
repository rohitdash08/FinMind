"""Weekly/monthly financial digest.

Generates summary reports of spending, income, category breakdowns,
and trends for a given period.
"""

from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category


def generate_digest(user_id: int, period: str = "weekly") -> dict:
    """Generate a financial digest for the given period.

    Args:
        user_id: User ID
        period: 'weekly' or 'monthly'
    """
    end = date.today()
    if period == "monthly":
        start = end.replace(day=1)
        prev_start = (start - timedelta(days=1)).replace(day=1)
        prev_end = start - timedelta(days=1)
    else:
        start = end - timedelta(days=6)  # last 7 days
        prev_start = start - timedelta(days=7)
        prev_end = start - timedelta(days=1)

    current = _period_stats(user_id, start, end)
    previous = _period_stats(user_id, prev_start, prev_end)

    # Comparison
    if previous["total"] > 0:
        change_pct = round((current["total"] - previous["total"]) / previous["total"] * 100, 1)
    else:
        change_pct = 100.0 if current["total"] > 0 else 0.0

    if change_pct > 10:
        trend = "up"
    elif change_pct < -10:
        trend = "down"
    else:
        trend = "stable"

    # Top categories
    top_cats = sorted(current["categories"], key=lambda x: x["total"], reverse=True)[:5]

    # Daily pattern
    daily = _daily_breakdown(user_id, start, end)

    # Highlights
    highlights = _generate_highlights(current, previous, change_pct, top_cats)

    return {
        "period": period,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "summary": {
            "total_spent": current["total"],
            "transaction_count": current["tx_count"],
            "daily_average": current["daily_avg"],
            "previous_total": previous["total"],
            "change_pct": change_pct,
            "trend": trend,
        },
        "top_categories": top_cats,
        "daily_breakdown": daily,
        "highlights": highlights,
    }


def get_digest_history(user_id: int, limit: int = 10) -> list[dict]:
    """Get recent period summaries for trend view."""
    results = []
    end = date.today()

    for i in range(limit):
        w_end = end - timedelta(weeks=i)
        w_start = w_end - timedelta(days=6)
        stats = _period_stats(user_id, w_start, w_end)
        results.append({
            "week": f"W-{i}",
            "start": w_start.isoformat(),
            "end": w_end.isoformat(),
            "total": stats["total"],
            "tx_count": stats["tx_count"],
        })

    return results


def _period_stats(user_id: int, start: date, end: date) -> dict:
    rows = (
        db.session.query(Category.name, func.sum(Expense.amount), func.count(Expense.id))
        .join(Category, Expense.category_id == Category.id)
        .filter(Expense.user_id == user_id, Expense.date >= start, Expense.date <= end)
        .group_by(Category.name)
        .all()
    )

    categories = []
    total = 0
    tx_count = 0
    for name, amount, count in rows:
        amt = float(amount)
        total += amt
        tx_count += count
        categories.append({"name": name, "total": round(amt, 2), "count": count})

    days = max((end - start).days + 1, 1)

    # Add percentages
    for c in categories:
        c["percentage"] = round(c["total"] / total * 100, 1) if total > 0 else 0

    return {
        "total": round(total, 2),
        "tx_count": tx_count,
        "daily_avg": round(total / days, 2),
        "categories": categories,
    }


def _daily_breakdown(user_id: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(Expense.date, func.sum(Expense.amount), func.count(Expense.id))
        .filter(Expense.user_id == user_id, Expense.date >= start, Expense.date <= end)
        .group_by(Expense.date)
        .all()
    )

    daily_map = {r[0]: {"amount": float(r[1]), "count": r[2]} for r in rows}
    result = []
    current = start
    while current <= end:
        d = daily_map.get(current, {"amount": 0, "count": 0})
        result.append({"date": current.isoformat(), "amount": round(d["amount"], 2), "count": d["count"]})
        current += timedelta(days=1)
    return result


def _generate_highlights(current: dict, previous: dict, change_pct: float, top_cats: list) -> list[str]:
    highlights = []

    if change_pct > 20:
        highlights.append(f"Spending increased {change_pct}% compared to the previous period.")
    elif change_pct < -20:
        highlights.append(f"Great job! Spending decreased {abs(change_pct)}% from last period.")
    else:
        highlights.append("Spending is relatively stable compared to last period.")

    if top_cats:
        top = top_cats[0]
        highlights.append(f"Top category: {top['name']} ({top['percentage']}% of spending, {top['total']:.0f} total).")

    if current["tx_count"] > 0:
        highlights.append(f"{current['tx_count']} transactions averaging {current['daily_avg']:.0f}/day.")

    return highlights
