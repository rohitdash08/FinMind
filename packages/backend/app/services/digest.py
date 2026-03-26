"""Weekly financial digest service.

Generates comprehensive weekly summaries with spending breakdowns,
week-over-week trend analysis, daily spending patterns, upcoming
bills alerts, and actionable insights derived from user behaviour.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Bill, Category, Expense

logger = logging.getLogger("finmind.digest")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def weekly_digest(
    user_id: int,
    week_str: str | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    """Return a full weekly financial digest for *user_id*.

    Parameters
    ----------
    user_id:
        Authenticated user id.
    week_str:
        ISO week string ``YYYY-Wnn`` (e.g. ``2026-W13``).  Defaults to
        the current ISO week.
    currency:
        Optional currency filter.  When supplied only expenses in that
        currency are included.

    Returns
    -------
    dict
        Digest payload ready for JSON serialisation.
    """
    current_start, current_end = _resolve_week(week_str)
    prev_start = current_start - timedelta(weeks=1)
    prev_end = current_end - timedelta(weeks=1)

    current_expenses = _fetch_expenses(user_id, current_start, current_end, currency)
    prev_expenses = _fetch_expenses(user_id, prev_start, prev_end, currency)

    category_breakdown = _category_breakdown(user_id, current_start, current_end, currency)
    prev_category_breakdown = _category_breakdown(user_id, prev_start, prev_end, currency)

    daily_pattern = _daily_pattern(user_id, current_start, current_end, currency)

    income_current = _total_by_type(user_id, current_start, current_end, "INCOME", currency)
    income_prev = _total_by_type(user_id, prev_start, prev_end, "INCOME", currency)
    expense_current = _total_by_type(user_id, current_start, current_end, "EXPENSE", currency)
    expense_prev = _total_by_type(user_id, prev_start, prev_end, "EXPENSE", currency)

    savings_current = income_current - expense_current
    savings_prev = income_prev - expense_prev

    trends = _compute_trends(
        category_breakdown, prev_category_breakdown,
        expense_current, expense_prev,
        income_current, income_prev,
    )

    upcoming_bills = _upcoming_bills(user_id, current_end, currency)

    insights = _generate_insights(
        income_current, income_prev,
        expense_current, expense_prev,
        savings_current, savings_prev,
        category_breakdown, prev_category_breakdown,
        daily_pattern, upcoming_bills,
    )

    iso_year, iso_week, _ = current_start.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"

    payload: dict[str, Any] = {
        "week": week_label,
        "period": {
            "start": current_start.isoformat(),
            "end": current_end.isoformat(),
        },
        "summary": {
            "total_income": _f(income_current),
            "total_expenses": _f(expense_current),
            "net_savings": _f(savings_current),
            "transaction_count": len(current_expenses),
        },
        "week_over_week": {
            "income_change": _pct_change(income_prev, income_current),
            "expense_change": _pct_change(expense_prev, expense_current),
            "savings_change": _pct_change(savings_prev, savings_current),
            "prev_total_expenses": _f(expense_prev),
            "prev_total_income": _f(income_prev),
        },
        "category_breakdown": category_breakdown,
        "daily_spending": daily_pattern,
        "trends": trends,
        "upcoming_bills": upcoming_bills,
        "insights": insights,
    }
    if currency:
        payload["currency"] = currency

    logger.info(
        "Weekly digest generated user=%s week=%s txn=%s",
        user_id, week_label, len(current_expenses),
    )
    return payload


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_week(week_str: str | None) -> tuple[date, date]:
    """Return (monday, sunday) for the given ISO week string."""
    if week_str:
        week_str = week_str.strip()
        parts = week_str.split("-W")
        if len(parts) != 2:
            raise ValueError(f"Invalid week format: {week_str!r}, expected YYYY-Wnn")
        year = int(parts[0])
        week = int(parts[1])
        if week < 1 or week > 53:
            raise ValueError(f"Week number out of range: {week}")
        monday = date.fromisocalendar(year, week, 1)
    else:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _fetch_expenses(
    user_id: int, start: date, end: date, currency: str | None,
) -> list[Expense]:
    q = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
    )
    if currency:
        q = q.filter(Expense.currency == currency)
    return q.all()


def _total_by_type(
    user_id: int, start: date, end: date, exp_type: str, currency: str | None,
) -> float:
    q = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
    )
    if exp_type == "EXPENSE":
        q = q.filter(Expense.expense_type != "INCOME")
    else:
        q = q.filter(Expense.expense_type == exp_type)
    if currency:
        q = q.filter(Expense.currency == currency)
    result = q.scalar()
    return float(result or 0)


def _category_breakdown(
    user_id: int, start: date, end: date, currency: str | None,
) -> list[dict[str, Any]]:
    q = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
            func.count(Expense.id).label("count"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == user_id),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
    )
    if currency:
        q = q.filter(Expense.currency == currency)
    rows = (
        q.group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    grand_total = sum(float(r.total or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": _f(float(r.total or 0)),
            "transaction_count": int(r.count),
            "share_pct": round(float(r.total or 0) / grand_total * 100, 2) if grand_total else 0,
        }
        for r in rows
    ]


def _daily_pattern(
    user_id: int, start: date, end: date, currency: str | None,
) -> list[dict[str, Any]]:
    result = []
    day = start
    while day <= end:
        q = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at == day,
                Expense.expense_type != "INCOME",
            )
        )
        if currency:
            q = q.filter(Expense.currency == currency)
        total = float(q.scalar() or 0)
        result.append({
            "date": day.isoformat(),
            "day_name": day.strftime("%A"),
            "amount": _f(total),
        })
        day += timedelta(days=1)
    return result


def _compute_trends(
    current_cats: list[dict], prev_cats: list[dict],
    expense_cur: float, expense_prev: float,
    income_cur: float, income_prev: float,
) -> list[dict[str, Any]]:
    """Generate trend observations comparing current vs previous week."""
    trends: list[dict[str, Any]] = []

    # Overall spending trend
    direction = _trend_direction(expense_prev, expense_cur)
    trends.append({
        "metric": "total_spending",
        "direction": direction,
        "change_pct": _pct_change(expense_prev, expense_cur),
        "description": _spending_trend_description(direction, expense_prev, expense_cur),
    })

    # Income trend
    inc_direction = _trend_direction(income_prev, income_cur)
    trends.append({
        "metric": "total_income",
        "direction": inc_direction,
        "change_pct": _pct_change(income_prev, income_cur),
        "description": _income_trend_description(inc_direction, income_prev, income_cur),
    })

    # Per-category trends
    prev_map = {c["category_name"]: c["amount"] for c in prev_cats}
    for cat in current_cats:
        name = cat["category_name"]
        cur_amt = cat["amount"]
        prev_amt = prev_map.get(name, 0)
        if prev_amt == 0 and cur_amt > 0:
            trends.append({
                "metric": f"category:{name}",
                "direction": "NEW",
                "change_pct": None,
                "description": f"New spending in {name} this week (${cur_amt:,.2f})",
            })
        elif prev_amt > 0:
            cat_dir = _trend_direction(prev_amt, cur_amt)
            change = _pct_change(prev_amt, cur_amt)
            if abs(change or 0) >= 15:
                trends.append({
                    "metric": f"category:{name}",
                    "direction": cat_dir,
                    "change_pct": change,
                    "description": f"{name} spending {'increased' if cat_dir == 'UP' else 'decreased'} by {abs(change or 0):.1f}%",
                })

    # Categories that vanished
    current_names = {c["category_name"] for c in current_cats}
    for prev_cat in prev_cats:
        if prev_cat["category_name"] not in current_names and prev_cat["amount"] > 0:
            trends.append({
                "metric": f"category:{prev_cat['category_name']}",
                "direction": "GONE",
                "change_pct": -100.0,
                "description": f"No {prev_cat['category_name']} spending this week (was ${prev_cat['amount']:,.2f})",
            })

    return trends


def _upcoming_bills(
    user_id: int, after_date: date, currency: str | None,
) -> list[dict[str, Any]]:
    """Bills due in the next 7 days after the digest period."""
    window_end = after_date + timedelta(days=7)
    q = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active.is_(True),
            Bill.next_due_date > after_date,
            Bill.next_due_date <= window_end,
        )
    )
    if currency:
        q = q.filter(Bill.currency == currency)
    bills = q.order_by(Bill.next_due_date.asc()).all()
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": _f(float(b.amount)),
            "currency": b.currency,
            "due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
            "autopay": b.autopay_enabled,
        }
        for b in bills
    ]


def _generate_insights(
    income_cur: float, income_prev: float,
    expense_cur: float, expense_prev: float,
    savings_cur: float, savings_prev: float,
    cats_cur: list[dict], cats_prev: list[dict],
    daily: list[dict], upcoming_bills: list[dict],
) -> list[dict[str, str]]:
    """Generate plain-English insights from the digest data."""
    insights: list[dict[str, str]] = []

    # 1. Savings health
    if income_cur > 0:
        savings_rate = savings_cur / income_cur * 100
        if savings_rate >= 20:
            insights.append({
                "type": "positive",
                "title": "Strong savings rate",
                "message": f"You saved {savings_rate:.0f}% of your income this week. Keep it up!",
            })
        elif savings_rate >= 0:
            insights.append({
                "type": "neutral",
                "title": "Savings rate",
                "message": f"You saved {savings_rate:.0f}% of your income. Aim for 20% to build a solid safety net.",
            })
        else:
            insights.append({
                "type": "warning",
                "title": "Spending exceeds income",
                "message": f"You spent ${abs(savings_cur):,.2f} more than you earned this week.",
            })

    # 2. Spending spike detection
    if expense_prev > 0:
        change = (expense_cur - expense_prev) / expense_prev * 100
        if change > 50:
            insights.append({
                "type": "warning",
                "title": "Spending spike detected",
                "message": f"Your spending jumped {change:.0f}% compared to last week. Review your transactions.",
            })
        elif change < -30:
            insights.append({
                "type": "positive",
                "title": "Spending reduction",
                "message": f"Great job! You cut spending by {abs(change):.0f}% compared to last week.",
            })

    # 3. Top category analysis
    if cats_cur:
        top = cats_cur[0]
        if top["share_pct"] >= 50:
            insights.append({
                "type": "neutral",
                "title": f"{top['category_name']} dominates spending",
                "message": (
                    f"{top['category_name']} accounts for {top['share_pct']:.0f}% "
                    f"of your spending. Consider diversifying your budget."
                ),
            })

    # 4. Category spike vs last week
    prev_map = {c["category_name"]: c["amount"] for c in cats_prev}
    for cat in cats_cur:
        prev_amt = prev_map.get(cat["category_name"], 0)
        if prev_amt > 0 and cat["amount"] > prev_amt * 3:
            multiplier = cat["amount"] / prev_amt
            insights.append({
                "type": "warning",
                "title": f"{cat['category_name']} anomaly",
                "message": (
                    f"You spent {multiplier:.1f}x more on {cat['category_name']} "
                    f"this week compared to last week."
                ),
            })

    # 5. Daily pattern insight
    if daily:
        amounts = [(d["date"], d["day_name"], d["amount"]) for d in daily if d["amount"] > 0]
        if amounts:
            peak = max(amounts, key=lambda x: x[2])
            insights.append({
                "type": "neutral",
                "title": "Peak spending day",
                "message": f"Your highest spending day was {peak[1]} (${peak[2]:,.2f}).",
            })

    # 6. Upcoming bills warning
    if upcoming_bills:
        total_due = sum(b["amount"] for b in upcoming_bills)
        non_autopay = [b for b in upcoming_bills if not b["autopay"]]
        if non_autopay:
            insights.append({
                "type": "warning",
                "title": "Bills due soon",
                "message": (
                    f"{len(non_autopay)} bill(s) totalling ${sum(b['amount'] for b in non_autopay):,.2f} "
                    f"are due next week without autopay. Don't forget to pay them!"
                ),
            })
        if total_due > 0:
            insights.append({
                "type": "neutral",
                "title": "Upcoming bill total",
                "message": f"${total_due:,.2f} in bills due over the next 7 days.",
            })

    # 7. No-spend days
    zero_days = [d for d in daily if d["amount"] == 0]
    if len(zero_days) >= 3:
        insights.append({
            "type": "positive",
            "title": "No-spend days",
            "message": f"You had {len(zero_days)} no-spend day(s) this week. Great discipline!",
        })

    return insights


# -- Utility helpers --

def _f(val: float) -> float:
    """Round to 2 decimal places for JSON output."""
    return round(val, 2)


def _pct_change(prev: float, cur: float) -> float | None:
    if prev == 0 and cur == 0:
        return 0.0
    if prev == 0:
        return None  # infinite change
    return round((cur - prev) / abs(prev) * 100, 2)


def _trend_direction(prev: float, cur: float) -> str:
    if cur > prev * 1.05:
        return "UP"
    if cur < prev * 0.95:
        return "DOWN"
    return "FLAT"


def _spending_trend_description(direction: str, prev: float, cur: float) -> str:
    if direction == "UP":
        return f"Spending increased from ${prev:,.2f} to ${cur:,.2f}"
    if direction == "DOWN":
        return f"Spending decreased from ${prev:,.2f} to ${cur:,.2f}"
    return f"Spending remained stable around ${cur:,.2f}"


def _income_trend_description(direction: str, prev: float, cur: float) -> str:
    if direction == "UP":
        return f"Income increased from ${prev:,.2f} to ${cur:,.2f}"
    if direction == "DOWN":
        return f"Income decreased from ${prev:,.2f} to ${cur:,.2f}"
    return f"Income remained stable around ${cur:,.2f}"
