from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, Category

bp = Blueprint("digest", __name__)

INSIGHTS = [
    "You're making great progress — keep it up!",
    "Small savings add up over time. Stay consistent!",
    "Tracking spending is the first step to financial freedom.",
    "Every dollar saved is a dollar earned.",
    "Awareness is power — you're already ahead of most people.",
]


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    today = date.today()
    week_start = today - timedelta(days=6)
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start - timedelta(days=1)

    # This week expenses
    this_week = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == uid, Expense.spent_at >= week_start, Expense.spent_at <= today)
        .scalar()
    )
    this_week_total = float(this_week or 0)

    # Last week expenses
    last_week = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == uid, Expense.spent_at >= prev_week_start, Expense.spent_at <= prev_week_end)
        .scalar()
    )
    last_week_total = float(last_week or 0)

    pct_change = 0.0
    if last_week_total > 0:
        pct_change = round(((this_week_total - last_week_total) / last_week_total) * 100, 1)

    # Top 3 categories
    cat_rows = (
        db.session.query(Category.name, func.sum(Expense.amount).label("total"))
        .join(Category, Expense.category_id == Category.id)
        .filter(Expense.user_id == uid, Expense.spent_at >= week_start, Expense.spent_at <= today)
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .limit(3)
        .all()
    )
    top_categories = [{"name": r[0], "amount": float(r[1])} for r in cat_rows]

    # Biggest single expense
    biggest = (
        db.session.query(Expense)
        .filter(Expense.user_id == uid, Expense.spent_at >= week_start, Expense.spent_at <= today)
        .order_by(Expense.amount.desc())
        .first()
    )
    biggest_expense = None
    if biggest:
        biggest_expense = {"description": biggest.notes or "", "amount": float(biggest.amount), "date": biggest.spent_at.isoformat()}

    # This week income
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == uid, Expense.expense_type == "INCOME", Expense.spent_at >= week_start, Expense.spent_at <= today)
        .scalar()
    )
    income_total = float(income or 0)
    expenses_only = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == uid, Expense.expense_type == "EXPENSE", Expense.spent_at >= week_start, Expense.spent_at <= today)
        .scalar()
    )
    expenses_total = float(expenses_only or 0)
    savings_rate = 0.0
    if income_total > 0:
        savings_rate = round(((income_total - expenses_total) / income_total) * 100, 1)

    insight = INSIGHTS[today.toordinal() % len(INSIGHTS)]

    return jsonify(
        total_spent=this_week_total,
        last_week_total=last_week_total,
        pct_change=pct_change,
        top_categories=top_categories,
        biggest_expense=biggest_expense,
        savings_rate=savings_rate,
        insight=insight,
        week_start=week_start.isoformat(),
        week_end=today.isoformat(),
    )
