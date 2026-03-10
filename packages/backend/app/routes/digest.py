"""Weekly financial digest — Smart summary of spending trends and insights."""

from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import extract, func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Expense, Category, Bill, AuditLog

bp = Blueprint("digest", __name__)


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Return a smart weekly financial summary with trends and insights."""
    uid = int(get_jwt_identity())
    ref_date_str = request.args.get("date")

    if ref_date_str:
        try:
            ref_date = date.fromisoformat(ref_date_str)
        except ValueError:
            return jsonify(error="invalid date, expected YYYY-MM-DD"), 400
    else:
        ref_date = date.today()

    week_end = ref_date
    week_start = week_end - timedelta(days=6)
    prev_week_end = week_start - timedelta(days=1)
    prev_week_start = prev_week_end - timedelta(days=6)

    digest = _build_digest(uid, week_start, week_end, prev_week_start, prev_week_end)

    AuditLog(user_id=uid, action="WEEKLY_DIGEST_VIEWED")
    try:
        db.session.add(AuditLog(user_id=uid, action="WEEKLY_DIGEST_VIEWED"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify(digest)


@bp.get("/weekly/history")
@jwt_required()
def digest_history():
    """Return digests for the last N weeks."""
    uid = int(get_jwt_identity())
    weeks = min(int(request.args.get("weeks", 4)), 12)
    ref_date = date.today()

    history = []
    for i in range(weeks):
        week_end = ref_date - timedelta(days=7 * i)
        week_start = week_end - timedelta(days=6)
        prev_week_end = week_start - timedelta(days=1)
        prev_week_start = prev_week_end - timedelta(days=6)
        summary = _build_digest(uid, week_start, week_end, prev_week_start, prev_week_end)
        history.append(summary)

    return jsonify({"weeks": weeks, "history": history})


def _build_digest(uid, week_start, week_end, prev_week_start, prev_week_end):
    """Build the digest payload for a single week."""
    current_expenses = _sum_expenses(uid, week_start, week_end)
    current_income = _sum_income(uid, week_start, week_end)
    prev_expenses = _sum_expenses(uid, prev_week_start, prev_week_end)
    prev_income = _sum_income(uid, prev_week_start, prev_week_end)

    expense_delta = _pct_change(prev_expenses, current_expenses)
    income_delta = _pct_change(prev_income, current_income)

    top_categories = _top_categories(uid, week_start, week_end)
    daily_breakdown = _daily_breakdown(uid, week_start, week_end)
    upcoming_bills = _upcoming_bills(uid, week_end)

    insights = _generate_insights(
        current_expenses, prev_expenses,
        current_income, prev_income,
        top_categories, upcoming_bills,
    )

    return {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
        },
        "summary": {
            "total_expenses": current_expenses,
            "total_income": current_income,
            "net_flow": round(current_income - current_expenses, 2),
            "expense_change_pct": expense_delta,
            "income_change_pct": income_delta,
        },
        "previous_period": {
            "total_expenses": prev_expenses,
            "total_income": prev_income,
        },
        "top_categories": top_categories,
        "daily_breakdown": daily_breakdown,
        "upcoming_bills": upcoming_bills,
        "insights": insights,
    }


def _sum_expenses(uid, start, end):
    """Sum non-income expenses in [start, end]."""
    result = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return round(float(result or 0), 2)


def _sum_income(uid, start, end):
    """Sum income entries in [start, end]."""
    result = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    return round(float(result or 0), 2)


def _pct_change(old_val, new_val):
    """Calculate percentage change, None if no previous data."""
    if old_val == 0:
        return None
    return round(((new_val - old_val) / old_val) * 100, 2)


def _top_categories(uid, start, end, limit=5):
    """Top spending categories for the period."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .limit(limit)
        .all()
    )
    total_spent = sum(float(r.total or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": round(float(r.total or 0), 2),
            "share_pct": (
                round((float(r.total or 0) / total_spent) * 100, 2)
                if total_spent > 0
                else 0
            ),
        }
        for r in rows
    ]


def _daily_breakdown(uid, start, end):
    """Per-day expense totals for the week."""
    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )
    day_map = {r.spent_at.isoformat(): round(float(r.total or 0), 2) for r in rows}
    result = []
    current = start
    while current <= end:
        result.append({
            "date": current.isoformat(),
            "amount": day_map.get(current.isoformat(), 0.0),
        })
        current += timedelta(days=1)
    return result


def _upcoming_bills(uid, ref_date, days_ahead=7):
    """Bills due within the next N days."""
    cutoff = ref_date + timedelta(days=days_ahead)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= ref_date,
            Bill.next_due_date <= cutoff,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": round(float(b.amount), 2),
            "currency": b.currency,
            "due_date": b.next_due_date.isoformat(),
        }
        for b in bills
    ]


def _generate_insights(
    current_expenses, prev_expenses,
    current_income, prev_income,
    top_categories, upcoming_bills,
):
    """Generate human-readable insights based on the data."""
    insights = []

    # Spending trend
    if prev_expenses > 0:
        pct = ((current_expenses - prev_expenses) / prev_expenses) * 100
        if pct > 15:
            insights.append({
                "type": "warning",
                "message": f"Spending increased {abs(pct):.0f}% compared to last week.",
            })
        elif pct < -10:
            insights.append({
                "type": "positive",
                "message": f"Great job! Spending decreased {abs(pct):.0f}% compared to last week.",
            })
        else:
            insights.append({
                "type": "neutral",
                "message": "Spending is roughly stable compared to last week.",
            })

    # Net flow
    net = current_income - current_expenses
    if net < 0:
        insights.append({
            "type": "warning",
            "message": f"You spent ${abs(net):.2f} more than you earned this week.",
        })
    elif net > 0:
        insights.append({
            "type": "positive",
            "message": f"You saved ${net:.2f} this week. Keep it up!",
        })

    # Top category alert
    if top_categories:
        top = top_categories[0]
        if top["share_pct"] > 50:
            insights.append({
                "type": "info",
                "message": f"{top['category_name']} accounts for {top['share_pct']:.0f}% of your spending.",
            })

    # Upcoming bills
    if upcoming_bills:
        total_due = sum(b["amount"] for b in upcoming_bills)
        insights.append({
            "type": "info",
            "message": f"{len(upcoming_bills)} bill(s) due soon, totaling ${total_due:.2f}.",
        })

    # No data case
    if current_expenses == 0 and current_income == 0:
        insights.append({
            "type": "info",
            "message": "No transactions recorded this week. Start tracking to get insights!",
        })

    return insights
