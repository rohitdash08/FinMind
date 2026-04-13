"""Weekly financial digest endpoint.

Provides intelligent weekly summaries with:
  - Total income / expenses / net flow
  - Per-category breakdown with percentage share
  - Week-over-week comparison (amount delta + percentage change)
  - Automated trend detection and actionable insights
"""

from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import extract, func

from ..extensions import db
from ..models import Expense, Category, Bill
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def _parse_week(week_str: str | None) -> tuple[date, date] | None:
    """Parse ISO week string (YYYY-WNN) into (monday, sunday) date range.

    Returns None on invalid input.
    """
    if not week_str:
        return None
    try:
        parts = week_str.split("-W")
        if len(parts) != 2:
            return None
        year = int(parts[0])
        week = int(parts[1])
        if week < 1 or week > 53:
            return None
        monday = date.fromisocalendar(year, week, 1)
        sunday = monday + timedelta(days=6)
        return monday, sunday
    except (ValueError, TypeError):
        return None


def _current_week_str() -> str:
    """Return current ISO week string, e.g. '2026-W15'."""
    today = date.today()
    iso = today.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _prev_week_str(week_str: str) -> str:
    """Return the previous week's ISO string."""
    parsed = _parse_week(week_str)
    if not parsed:
        return ""
    monday = parsed[0] - timedelta(days=7)
    iso = monday.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _query_week_expenses(uid: int, start: date, end: date) -> list:
    """Query all expenses in a date range for a user."""
    return (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .all()
    )


def _aggregate(expenses: list) -> dict:
    """Aggregate expenses into income, expenses, net_flow, and category breakdown."""
    total_income = Decimal("0")
    total_expense = Decimal("0")
    categories: dict[int | None, dict] = {}

    for e in expenses:
        amount = Decimal(str(e.amount))
        if e.expense_type == "INCOME":
            total_income += amount
        else:
            total_expense += amount
            cat_id = e.category_id
            if cat_id not in categories:
                categories[cat_id] = {"amount": Decimal("0"), "count": 0}
            categories[cat_id]["amount"] += amount
            categories[cat_id]["count"] += 1

    return {
        "income": total_income,
        "expenses": total_expense,
        "net_flow": total_income - total_expense,
        "categories": categories,
    }


def _compute_wow(current: dict, previous: dict) -> dict:
    """Compute week-over-week comparison metrics."""
    prev_expenses = float(previous.get("expenses", 0))
    curr_expenses = float(current.get("expenses", 0))
    prev_income = float(previous.get("income", 0))
    curr_income = float(current.get("income", 0))

    expense_delta = curr_expenses - prev_expenses
    income_delta = curr_income - prev_income

    expense_pct = (
        round((expense_delta / prev_expenses) * 100, 1)
        if prev_expenses > 0
        else (100.0 if curr_expenses > 0 else 0.0)
    )
    income_pct = (
        round((income_delta / prev_income) * 100, 1)
        if prev_income > 0
        else (100.0 if curr_income > 0 else 0.0)
    )

    return {
        "expense_delta": round(expense_delta, 2),
        "expense_pct_change": expense_pct,
        "income_delta": round(income_delta, 2),
        "income_pct_change": income_pct,
        "previous_week_expenses": round(prev_expenses, 2),
        "previous_week_income": round(prev_income, 2),
    }


def _generate_insights(
    current_agg: dict,
    previous_agg: dict,
    category_names: dict[int | None, str],
) -> list[dict]:
    """Generate actionable insights based on spending patterns."""
    insights = []

    curr_expenses = float(current_agg["expenses"])
    prev_expenses = float(previous_agg.get("expenses", 0))

    # Spending trend insight
    if prev_expenses > 0:
        pct_change = ((curr_expenses - prev_expenses) / prev_expenses) * 100
        if pct_change > 20:
            insights.append({
                "type": "warning",
                "title": "Spending Spike",
                "message": (
                    f"Your spending increased by {abs(pct_change):.0f}% this week "
                    f"compared to last week."
                ),
            })
        elif pct_change < -20:
            insights.append({
                "type": "positive",
                "title": "Great Savings",
                "message": (
                    f"You spent {abs(pct_change):.0f}% less this week "
                    f"compared to last week. Keep it up!"
                ),
            })

    # Top category insight
    categories = current_agg.get("categories", {})
    if categories and curr_expenses > 0:
        top_cat_id = max(categories, key=lambda k: float(categories[k]["amount"]))
        top_amount = float(categories[top_cat_id]["amount"])
        top_pct = (top_amount / curr_expenses) * 100
        cat_name = category_names.get(top_cat_id, "Uncategorized")

        if top_pct > 50:
            insights.append({
                "type": "info",
                "title": "Dominant Category",
                "message": (
                    f"'{cat_name}' accounts for {top_pct:.0f}% of your spending "
                    f"this week (${top_amount:,.2f})."
                ),
            })

    # Category spike detection (WoW per category)
    prev_categories = previous_agg.get("categories", {})
    for cat_id, data in categories.items():
        curr_cat_total = float(data["amount"])
        prev_cat_total = float(
            prev_categories.get(cat_id, {}).get("amount", 0)
        )
        if prev_cat_total > 0:
            cat_pct = ((curr_cat_total - prev_cat_total) / prev_cat_total) * 100
            cat_name = category_names.get(cat_id, "Uncategorized")
            if cat_pct > 50 and curr_cat_total > 10:
                insights.append({
                    "type": "warning",
                    "title": f"Spike in '{cat_name}'",
                    "message": (
                        f"Spending in '{cat_name}' jumped {cat_pct:.0f}% "
                        f"(${prev_cat_total:,.2f} → ${curr_cat_total:,.2f})."
                    ),
                })

    # Net flow insight
    net_flow = float(current_agg["net_flow"])
    if net_flow < 0:
        insights.append({
            "type": "warning",
            "title": "Negative Cash Flow",
            "message": (
                f"You spent ${abs(net_flow):,.2f} more than you earned this week."
            ),
        })
    elif net_flow > 0 and curr_expenses > 0:
        insights.append({
            "type": "positive",
            "title": "Positive Cash Flow",
            "message": (
                f"You saved ${net_flow:,.2f} this week after all expenses."
            ),
        })

    # No spending insight
    if curr_expenses == 0 and prev_expenses == 0:
        insights.append({
            "type": "info",
            "title": "No Activity",
            "message": "No expenses recorded for this week or last week.",
        })

    return insights


def _resolve_category_names(uid: int, cat_ids: set) -> dict[int | None, str]:
    """Resolve category IDs to their names."""
    names: dict[int | None, str] = {None: "Uncategorized"}
    if not cat_ids:
        return names
    valid_ids = [c for c in cat_ids if c is not None]
    if not valid_ids:
        return names
    rows = (
        db.session.query(Category.id, Category.name)
        .filter(Category.id.in_(valid_ids), Category.user_id == uid)
        .all()
    )
    for row in rows:
        names[row.id] = row.name
    return names


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Get a weekly financial digest.

    Query params:
      - week: ISO week string, e.g. '2026-W15' (defaults to current week)

    Returns a comprehensive digest with:
      - Summary (income, expenses, net flow)
      - Category breakdown with percentage shares
      - Week-over-week comparison
      - Trend detection and actionable insights
    """
    uid = int(get_jwt_identity())
    week_str = (request.args.get("week") or "").strip()

    if not week_str:
        week_str = _current_week_str()

    week_range = _parse_week(week_str)
    if not week_range:
        return jsonify(error="invalid week format, expected YYYY-WNN"), 400

    start, end = week_range

    # Check cache
    cache_key = f"digest:weekly:{uid}:{week_str}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    # Current week data
    current_expenses = _query_week_expenses(uid, start, end)
    current_agg = _aggregate(current_expenses)

    # Previous week data (for WoW comparison)
    prev_week_str = _prev_week_str(week_str)
    prev_range = _parse_week(prev_week_str)
    previous_agg = {"income": Decimal("0"), "expenses": Decimal("0"),
                    "net_flow": Decimal("0"), "categories": {}}
    if prev_range:
        prev_expenses = _query_week_expenses(uid, prev_range[0], prev_range[1])
        previous_agg = _aggregate(prev_expenses)

    # Resolve category names
    all_cat_ids = set(current_agg["categories"].keys()) | set(
        previous_agg.get("categories", {}).keys()
    )
    category_names = _resolve_category_names(uid, all_cat_ids)

    # Build category breakdown
    total_expenses = float(current_agg["expenses"])
    category_breakdown = []
    for cat_id, data in sorted(
        current_agg["categories"].items(),
        key=lambda x: float(x[1]["amount"]),
        reverse=True,
    ):
        amount = float(data["amount"])
        prev_cat_amount = float(
            previous_agg.get("categories", {}).get(cat_id, {}).get("amount", 0)
        )
        category_breakdown.append({
            "category_id": cat_id,
            "category_name": category_names.get(cat_id, "Uncategorized"),
            "amount": round(amount, 2),
            "count": data["count"],
            "share_pct": round((amount / total_expenses) * 100, 1)
            if total_expenses > 0
            else 0.0,
            "wow_delta": round(amount - prev_cat_amount, 2),
        })

    # WoW metrics
    wow = _compute_wow(
        {"expenses": current_agg["expenses"], "income": current_agg["income"]},
        {"expenses": previous_agg.get("expenses", 0),
         "income": previous_agg.get("income", 0)},
    )

    # Generate insights
    insights = _generate_insights(current_agg, previous_agg, category_names)

    # Top transactions (highest amounts)
    top_transactions = sorted(
        [e for e in current_expenses if e.expense_type != "INCOME"],
        key=lambda e: float(e.amount),
        reverse=True,
    )[:5]

    # Daily spending breakdown
    daily_spending: dict[str, float] = {}
    for e in current_expenses:
        if e.expense_type != "INCOME":
            day_str = e.spent_at.isoformat()
            daily_spending[day_str] = daily_spending.get(day_str, 0) + float(e.amount)

    # Build full 7-day array
    daily_data = []
    for i in range(7):
        day = start + timedelta(days=i)
        day_str = day.isoformat()
        daily_data.append({
            "date": day_str,
            "day_name": day.strftime("%A"),
            "amount": round(daily_spending.get(day_str, 0), 2),
        })

    payload = {
        "week": week_str,
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "summary": {
            "total_income": round(float(current_agg["income"]), 2),
            "total_expenses": round(float(current_agg["expenses"]), 2),
            "net_flow": round(float(current_agg["net_flow"]), 2),
            "transaction_count": len(current_expenses),
        },
        "category_breakdown": category_breakdown,
        "week_over_week": wow,
        "daily_spending": daily_data,
        "top_transactions": [
            {
                "id": e.id,
                "description": e.notes or "",
                "amount": round(float(e.amount), 2),
                "date": e.spent_at.isoformat(),
                "category_id": e.category_id,
            }
            for e in top_transactions
        ],
        "insights": insights,
        "trends": {
            "spending_direction": (
                "up" if wow["expense_pct_change"] > 5
                else "down" if wow["expense_pct_change"] < -5
                else "stable"
            ),
            "income_direction": (
                "up" if wow["income_pct_change"] > 5
                else "down" if wow["income_pct_change"] < -5
                else "stable"
            ),
        },
    }

    # Cache for 5 minutes
    cache_set(cache_key, payload, ttl_seconds=300)

    logger.info("Weekly digest served user=%s week=%s", uid, week_str)
    return jsonify(payload)
