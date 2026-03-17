from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Expense, Category
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """GET /digest/weekly – Weekly financial summary for the authenticated user.

    Returns a JSON digest covering the last 7 days vs the prior 7 days,
    including summary totals, trend percentages, per-category breakdown,
    and human-readable insights.

    Returns:
        200: Weekly digest JSON object.
        401: Missing or invalid JWT.
    """
    user_id = int(get_jwt_identity())
    today = date.today()
    week_end = today
    week_start = today - timedelta(days=7)
    prior_end = week_start
    prior_start = week_start - timedelta(days=7)

    def _fetch(start, end):
        """Return (Expense, category_name) rows for the given date range."""
        return (
            db.session.query(Expense, Category.name.label("cat_name"))
            .outerjoin(Category, Expense.category_id == Category.id)
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= start,
                Expense.spent_at < end,
            )
            .all()
        )

    def _to_float(v):
        """Coerce Decimal / None to float."""
        if v is None:
            return 0.0
        return float(v)

    cur_rows = _fetch(week_start, week_end)
    prior_rows = _fetch(prior_start, prior_end)

    # expense_type: 'EXPENSE' | 'INCOME'
    def _expenses(rows):
        return [(e, c) for e, c in rows if (e.expense_type or "EXPENSE").upper() == "EXPENSE"]

    def _income(rows):
        return [(e, c) for e, c in rows if (e.expense_type or "EXPENSE").upper() == "INCOME"]

    cur_exp = _expenses(cur_rows)
    cur_inc = _income(cur_rows)
    prior_exp = _expenses(prior_rows)
    prior_inc = _income(prior_rows)

    total_expenses = sum(_to_float(e.amount) for e, _ in cur_exp)
    total_income = sum(_to_float(e.amount) for e, _ in cur_inc)
    net_flow = total_income - total_expenses
    transaction_count = len(cur_rows)

    prior_total_expenses = sum(_to_float(e.amount) for e, _ in prior_exp)
    prior_total_income = sum(_to_float(e.amount) for e, _ in prior_inc)

    def _pct_change(current, prior):
        if prior == 0:
            return 0.0
        return round((current - prior) / prior * 100, 1)

    expenses_vs_prior = _pct_change(total_expenses, prior_total_expenses)
    income_vs_prior = _pct_change(total_income, prior_total_income)

    # ── Category breakdown (expenses only) ──────────────────────────────────
    cat_totals = {}
    for expense, cat_name in cur_exp:
        cat = cat_name or "Uncategorized"
        if cat not in cat_totals:
            cat_totals[cat] = {"total": 0.0, "count": 0}
        cat_totals[cat]["total"] += _to_float(expense.amount)
        cat_totals[cat]["count"] += 1

    category_breakdown = [
        {
            "category": cat,
            "total": round(data["total"], 2),
            "pct_of_expenses": (
                round(data["total"] / total_expenses * 100, 1)
                if total_expenses
                else 0.0
            ),
            "count": data["count"],
        }
        for cat, data in sorted(cat_totals.items(), key=lambda x: -x[1]["total"])
    ]

    top_spending_category = (
        category_breakdown[0]["category"] if category_breakdown else None
    )

    biggest_expense = None
    if cur_exp:
        biggest_row, biggest_cat = max(cur_exp, key=lambda x: _to_float(x[0].amount))
        biggest_expense = {
            "amount": round(_to_float(biggest_row.amount), 2),
            "notes": biggest_row.notes or "",
            "category": biggest_cat or "Uncategorized",
        }

    # ── Insights ─────────────────────────────────────────────────────────────
    insights = []
    if expenses_vs_prior < 0:
        insights.append(f"You spent {abs(expenses_vs_prior)}% less than last week")
    elif expenses_vs_prior > 0:
        insights.append(f"You spent {expenses_vs_prior}% more than last week")
    else:
        insights.append("Your spending is unchanged from last week")
    if top_spending_category:
        insights.append(
            f"{top_spending_category} is your biggest spending category this week"
        )
    if net_flow > 0:
        insights.append(f"You saved {round(net_flow, 2)} this week")
    elif net_flow < 0:
        insights.append(f"You overspent by {round(abs(net_flow), 2)} this week")

    return jsonify(
        period={
            "start": week_start.strftime("%Y-%m-%d"),
            "end": week_end.strftime("%Y-%m-%d"),
        },
        summary=dict(
            total_expenses=round(total_expenses, 2),
            total_income=round(total_income, 2),
            net_flow=round(net_flow, 2),
            transaction_count=transaction_count,
        ),
        trends=dict(
            expenses_vs_prior_week_pct=expenses_vs_prior,
            income_vs_prior_week_pct=income_vs_prior,
            top_spending_category=top_spending_category,
            biggest_expense=biggest_expense,
        ),
        category_breakdown=category_breakdown,
        insights=insights,
    )
