"""Weekly digest service – aggregates expenses into a weekly summary."""

from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category


def _week_bounds(year: int, week: int) -> tuple[date, date]:
    """Return (monday, sunday) for ISO year/week."""
    jan4 = date(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start_of_week1 + timedelta(weeks=week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _aggregate_by_category(user_id: int, start: date, end: date) -> dict:
    """Return {category_name: total} for the given date range."""
    rows = (
        db.session.query(
            func.coalesce(Category.name, "Uncategorized").label("cat_name"),
            func.sum(Expense.amount).label("total"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(Expense.user_id == user_id)
        .filter(Expense.spent_at >= start)
        .filter(Expense.spent_at <= end)
        .group_by("cat_name")
        .all()
    )
    return {row.cat_name: float(row.total) for row in rows}


def weekly_digest(user_id: int, year: int, week: int) -> dict:
    """Build weekly digest for *user_id* and ISO *year*/*week*."""
    start, end = _week_bounds(year, week)
    prev_start, prev_end = _week_bounds(year if week > 1 else year - 1, week - 1 if week > 1 else 52)

    current = _aggregate_by_category(user_id, start, end)
    previous = _aggregate_by_category(user_id, prev_start, prev_end)

    total_spent = round(sum(current.values()), 2)
    prev_total = round(sum(previous.values()), 2)

    # Week-over-week by category
    all_cats = sorted(set(list(current.keys()) + list(previous.keys())))
    wow = {}
    for cat in all_cats:
        cur = current.get(cat, 0.0)
        prev = previous.get(cat, 0.0)
        change = round(cur - prev, 2)
        pct = round((change / prev) * 100, 1) if prev else (100.0 if cur > 0 else 0.0)
        wow[cat] = {"current": cur, "previous": prev, "change": change, "change_pct": pct}

    # Trends
    trends = []
    if current:
        top_cat = max(current, key=current.get)
        trends.append(f"Top spending category: {top_cat} ({current[top_cat]:.2f})")

    if wow:
        biggest_inc = max(wow, key=lambda c: wow[c]["change"])
        biggest_dec = min(wow, key=lambda c: wow[c]["change"])
        if wow[biggest_inc]["change"] > 0:
            trends.append(
                f"Biggest increase: {biggest_inc} (+{wow[biggest_inc]['change']:.2f}, "
                f"+{wow[biggest_inc]['change_pct']}%)"
            )
        if wow[biggest_dec]["change"] < 0:
            trends.append(
                f"Biggest decrease: {biggest_dec} ({wow[biggest_dec]['change']:.2f}, "
                f"{wow[biggest_dec]['change_pct']}%)"
            )

    # Insights
    insights = []
    if prev_total > 0:
        overall_pct = round(((total_spent - prev_total) / prev_total) * 100, 1)
        direction = "more" if overall_pct > 0 else "less"
        insights.append(
            f"You spent {abs(overall_pct)}% {direction} this week compared to last week."
        )
    elif total_spent > 0:
        insights.append("This is your first tracked week – keep logging expenses!")

    if total_spent == 0:
        insights.append("No expenses recorded this week.")

    return {
        "week": f"{year}-W{week:02d}",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "total_spent": total_spent,
        "category_breakdown": current,
        "week_over_week_change": wow,
        "trends": trends,
        "insights": insights,
    }
