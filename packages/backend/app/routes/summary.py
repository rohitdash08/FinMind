"""
routes/summary.py — Smart Weekly Digest endpoint
Issue #121 · rohitdash08/FinMind
Author: Xavier Abraham Sandoval <abrahamsandoval.as@gmail.com>
"""

from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import Category, Expense

bp = Blueprint("summary", __name__)


def _week_bounds(offset: int = 0) -> tuple[date, date]:
    """Return (monday, sunday) for the current week minus `offset` weeks."""
    today = date.today()
    monday = today - timedelta(days=today.weekday()) - timedelta(weeks=offset)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _aggregate_week(user_id: int, start: date, end: date) -> dict:
    """Aggregate expenses and income for a user in [start, end]."""
    rows = (
        db.session.query(
            Expense.expense_type,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Expense.expense_type)
        .all()
    )

    totals = {"EXPENSE": Decimal("0"), "INCOME": Decimal("0")}
    counts = {"EXPENSE": 0, "INCOME": 0}
    for row in rows:
        key = row.expense_type.upper()
        if key in totals:
            totals[key] = row.total or Decimal("0")
            counts[key] = row.count or 0

    net = totals["INCOME"] - totals["EXPENSE"]
    return {
        "total_expenses": float(totals["EXPENSE"]),
        "total_income": float(totals["INCOME"]),
        "net": float(net),
        "expense_count": counts["EXPENSE"],
        "income_count": counts["INCOME"],
    }


def _category_breakdown(user_id: int, start: date, end: date) -> list[dict]:
    """Return per-category spending sorted by amount desc."""
    rows = (
        db.session.query(
            Category.name,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .join(Category, Expense.category_id == Category.id, isouter=True)
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    return [
        {
            "category": row.name or "Uncategorized",
            "amount": float(row.total or 0),
            "count": row.count or 0,
        }
        for row in rows
    ]


def _daily_trend(user_id: int, start: date, end: date) -> list[dict]:
    """Return daily expense totals for sparkline charts."""
    rows = (
        db.session.query(
            Expense.spent_at,
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )

    # Fill all days even if no data
    day_map = {row.spent_at: float(row.total or 0) for row in rows}
    trend = []
    current = start
    while current <= end:
        trend.append({"date": current.isoformat(), "amount": day_map.get(current, 0.0)})
        current += timedelta(days=1)
    return trend


def _generate_insights(current: dict, previous: dict) -> list[str]:
    """Generate human-readable insight strings comparing two weeks."""
    insights = []

    exp_curr = current["total_expenses"]
    exp_prev = previous["total_expenses"]

    if exp_prev > 0:
        pct = ((exp_curr - exp_prev) / exp_prev) * 100
        direction = "increased" if pct > 0 else "decreased"
        insights.append(
            f"Total spending {direction} by {abs(pct):.1f}% vs last week "
            f"({exp_prev:.2f} → {exp_curr:.2f})."
        )
    elif exp_curr > 0:
        insights.append(f"First week of recorded expenses: {exp_curr:.2f} total.")

    net = current["net"]
    if net >= 0:
        insights.append(f"Positive cash flow this week: +{net:.2f}.")
    else:
        insights.append(f"Negative cash flow this week: {net:.2f}. Consider reviewing discretionary spend.")

    return insights


# ── Public endpoint ────────────────────────────────────────────────────────────

@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """
    GET /summary/weekly?weeks_back=0

    Returns a structured weekly financial digest for the authenticated user.
    weeks_back=0  → current week
    weeks_back=1  → last week
    weeks_back=N  → N weeks ago
    """
    uid = int(get_jwt_identity())

    try:
        weeks_back = max(0, int(request.args.get("weeks_back", "0")))
    except ValueError:
        return jsonify(error="weeks_back must be an integer"), 400

    curr_start, curr_end = _week_bounds(offset=weeks_back)
    prev_start, prev_end = _week_bounds(offset=weeks_back + 1)

    current = _aggregate_week(uid, curr_start, curr_end)
    previous = _aggregate_week(uid, prev_start, prev_end)
    categories = _category_breakdown(uid, curr_start, curr_end)
    daily_trend = _daily_trend(uid, curr_start, curr_end)
    insights = _generate_insights(current, previous)

    return jsonify(
        {
            "period": {
                "start": curr_start.isoformat(),
                "end": curr_end.isoformat(),
                "label": f"Week of {curr_start.strftime('%b %d, %Y')}",
            },
            "summary": current,
            "previous_week": previous,
            "category_breakdown": categories,
            "daily_trend": daily_trend,
            "insights": insights,
        }
    )
