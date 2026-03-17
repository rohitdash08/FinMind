"""
Weekly financial digest endpoint.

GET /digest/weekly?week_start=YYYY-MM-DD
  Returns a weekly summary for the 7-day window starting on week_start
  (defaults to the most recent Monday). Includes:
    - total_spent, total_income, net_flow
    - category_breakdown with week-over-week delta
    - top_spending_category, biggest_increase, biggest_decrease
    - upcoming_bills in the next 7 days
    - insights[] — human-readable trend sentences

Responses are cached in Redis for 1 hour (falls back gracefully if Redis
is unavailable).
"""

from datetime import date, timedelta
from sqlalchemy import func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Expense, Category, Bill
from ..services.cache import cache_get, cache_set

bp = Blueprint("digest", __name__)

_CACHE_TTL = 3600  # 1 hour


def _monday(d: date) -> date:
    """Return the Monday on or before d."""
    return d - timedelta(days=d.weekday())


def _parse_week_start(raw: str | None) -> date:
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return _monday(date.today())


def _week_expenses(uid: int, start: date) -> list:
    """Return (category_name, total) rows for the given 7-day window."""
    end = start + timedelta(days=6)
    rows = (
        db.session.query(
            func.coalesce(Category.name, "Uncategorised").label("category"),
            func.sum(Expense.amount).label("total"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    return [(r.category, float(r.total)) for r in rows]


def _week_income(uid: int, start: date) -> float:
    end = start + timedelta(days=6)
    val = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    return float(val or 0)


def _upcoming_bills(uid: int, from_date: date, days: int = 7) -> list:
    to_date = from_date + timedelta(days=days)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= from_date,
            Bill.next_due_date <= to_date,
        )
        .order_by(Bill.next_due_date)
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "due_date": b.next_due_date.isoformat(),
        }
        for b in bills
    ]


def _build_insights(
    current_breakdown: list,
    prev_breakdown: list,
    total_spent: float,
    prev_total: float,
    upcoming: list,
) -> list[str]:
    insights = []

    # Week-over-week total
    if prev_total > 0:
        change_pct = ((total_spent - prev_total) / prev_total) * 100
        if abs(change_pct) >= 5:
            direction = "up" if change_pct > 0 else "down"
            insights.append(
                f"Total spending is {direction} {abs(change_pct):.0f}% compared to last week "
                f"({_fmt(prev_total)} → {_fmt(total_spent)})."
            )
    elif total_spent > 0:
        insights.append(f"You spent {_fmt(total_spent)} this week.")

    # Biggest category
    if current_breakdown:
        top_cat, top_amt = current_breakdown[0]
        pct = (top_amt / total_spent * 100) if total_spent > 0 else 0
        insights.append(
            f"{top_cat} is your top spending category at {_fmt(top_amt)} ({pct:.0f}% of total)."
        )

    # Category deltas
    prev_map = dict(prev_breakdown)
    curr_map = dict(current_breakdown)
    deltas = []
    for cat, amt in curr_map.items():
        prev_amt = prev_map.get(cat, 0)
        if prev_amt > 0:
            delta_pct = ((amt - prev_amt) / prev_amt) * 100
            deltas.append((cat, delta_pct, amt - prev_amt))

    if deltas:
        deltas.sort(key=lambda x: x[1], reverse=True)
        biggest_up = deltas[0]
        if biggest_up[1] >= 20:
            insights.append(
                f"{biggest_up[0]} spending increased by {biggest_up[1]:.0f}% vs last week "
                f"(+{_fmt(biggest_up[2])})."
            )
        biggest_down = deltas[-1]
        if biggest_down[1] <= -20:
            insights.append(
                f"{biggest_down[0]} spending decreased by {abs(biggest_down[1]):.0f}% vs last week "
                f"({_fmt(biggest_down[2])})."
            )

    # Upcoming bills
    if upcoming:
        names = ", ".join(b["name"] for b in upcoming[:3])
        suffix = f" and {len(upcoming) - 3} more" if len(upcoming) > 3 else ""
        insights.append(f"Bills due this week: {names}{suffix}.")

    if not insights:
        insights.append("No significant spending activity this week.")

    return insights


def _fmt(amount: float) -> str:
    return f"₹{amount:,.2f}"


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    week_start = _parse_week_start(request.args.get("week_start"))
    week_end = week_start + timedelta(days=6)
    prev_start = week_start - timedelta(days=7)

    cache_key = f"digest:weekly:{uid}:{week_start.isoformat()}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    current = _week_expenses(uid, week_start)
    previous = _week_expenses(uid, prev_start)
    income = _week_income(uid, week_start)
    upcoming = _upcoming_bills(uid, date.today())

    total_spent = sum(amt for _, amt in current)
    prev_total = sum(amt for _, amt in previous)

    category_breakdown = []
    prev_map = dict(previous)
    for cat, amt in current:
        prev_amt = prev_map.get(cat, 0)
        delta = amt - prev_amt
        delta_pct = ((delta / prev_amt) * 100) if prev_amt > 0 else None
        category_breakdown.append({
            "category": cat,
            "total": amt,
            "previous_total": prev_amt,
            "delta": round(delta, 2),
            "delta_pct": round(delta_pct, 1) if delta_pct is not None else None,
        })

    payload = {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "summary": {
            "total_spent": round(total_spent, 2),
            "total_income": round(income, 2),
            "net_flow": round(income - total_spent, 2),
            "prev_week_spent": round(prev_total, 2),
            "wow_change_pct": round(
                ((total_spent - prev_total) / prev_total * 100), 1
            ) if prev_total > 0 else None,
        },
        "category_breakdown": category_breakdown,
        "top_spending_category": current[0][0] if current else None,
        "upcoming_bills": upcoming,
        "insights": _build_insights(current, previous, total_spent, prev_total, upcoming),
    }

    try:
        cache_set(cache_key, payload, ttl_seconds=_CACHE_TTL)
    except Exception:
        pass  # Redis unavailable — serve uncached

    return jsonify(payload)
