"""Weekly financial digest service.

Generates smart summaries highlighting spending trends, category shifts,
and actionable insights by comparing the target week with the previous week.
"""

from datetime import date, timedelta
from sqlalchemy import func, extract
from ..extensions import db
from ..models import Expense, Category


def _week_bounds(ref_date: date | None = None):
    """Return (monday, sunday) of the week containing *ref_date*."""
    d = ref_date or date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _category_totals(user_id: int, start: date, end: date) -> dict:
    """Sum expenses per category name for a date range."""
    rows = (
        db.session.query(Category.name, func.sum(Expense.amount))
        .join(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == user_id,
            Expense.date >= start,
            Expense.date <= end,
        )
        .group_by(Category.name)
        .all()
    )
    return {name: float(total) for name, total in rows}


def _total(totals: dict) -> float:
    return sum(totals.values())


def _top_categories(totals: dict, n: int = 3) -> list[dict]:
    sorted_cats = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    return [{"category": name, "amount": amt} for name, amt in sorted_cats[:n]]


def _trend(current: float, previous: float) -> dict:
    if previous == 0:
        pct = 100.0 if current > 0 else 0.0
    else:
        pct = round((current - previous) / previous * 100, 1)
    direction = "up" if pct > 0 else ("down" if pct < 0 else "flat")
    return {"change_pct": pct, "direction": direction}


def _category_trends(current: dict, previous: dict) -> list[dict]:
    all_cats = set(current) | set(previous)
    trends = []
    for cat in all_cats:
        cur = current.get(cat, 0)
        prev = previous.get(cat, 0)
        t = _trend(cur, prev)
        trends.append({
            "category": cat,
            "current_amount": cur,
            "previous_amount": prev,
            **t,
        })
    trends.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    return trends


def _generate_insights(total_trend: dict, cat_trends: list[dict]) -> list[str]:
    insights = []
    if total_trend["direction"] == "up" and total_trend["change_pct"] > 20:
        insights.append(
            f"Spending increased {total_trend['change_pct']}% compared to last week. "
            "Consider reviewing discretionary expenses."
        )
    elif total_trend["direction"] == "down":
        insights.append(
            f"Great job! Spending decreased {abs(total_trend['change_pct'])}% from last week."
        )

    for ct in cat_trends[:2]:
        if ct["change_pct"] > 50 and ct["current_amount"] > 0:
            insights.append(
                f"{ct['category']} spending surged {ct['change_pct']}% — "
                f"from {ct['previous_amount']:.2f} to {ct['current_amount']:.2f}."
            )
        elif ct["change_pct"] < -50 and ct["previous_amount"] > 0:
            insights.append(
                f"{ct['category']} spending dropped {abs(ct['change_pct'])}% — nice saving!"
            )

    if not insights:
        insights.append("Spending is stable compared to last week. Keep it up!")

    return insights


def weekly_digest(user_id: int, ref_date: date | None = None) -> dict:
    """Build a weekly financial digest for *user_id*.

    Returns a dict with current/previous week totals, top categories,
    category-level trends, and actionable insights.
    """
    cur_start, cur_end = _week_bounds(ref_date)
    prev_start = cur_start - timedelta(days=7)
    prev_end = cur_start - timedelta(days=1)

    cur_totals = _category_totals(user_id, cur_start, cur_end)
    prev_totals = _category_totals(user_id, prev_start, prev_end)

    cur_total = _total(cur_totals)
    prev_total = _total(prev_totals)

    return {
        "week": {
            "start": cur_start.isoformat(),
            "end": cur_end.isoformat(),
        },
        "previous_week": {
            "start": prev_start.isoformat(),
            "end": prev_end.isoformat(),
        },
        "current_total": round(cur_total, 2),
        "previous_total": round(prev_total, 2),
        "total_trend": _trend(cur_total, prev_total),
        "top_categories": _top_categories(cur_totals),
        "category_trends": _category_trends(cur_totals, prev_totals),
        "insights": _generate_insights(
            _trend(cur_total, prev_total),
            _category_trends(cur_totals, prev_totals),
        ),
    }
