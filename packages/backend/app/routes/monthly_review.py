import logging
from datetime import date
from sqlalchemy import extract, func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Expense, Category

bp = Blueprint("monthly_review", __name__)
logger = logging.getLogger("finmind.monthly_review")


def _is_valid_month(ym: str) -> bool:
    if len(ym) != 7 or ym[4] != "-":
        return False
    parts = ym.split("-")
    if not (parts[0].isdigit() and parts[1].isdigit()):
        return False
    m = int(parts[1])
    return 1 <= m <= 12


def _get_month_totals(uid, year, month):
    income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return income, expenses


def _top_categories(uid, year, month, limit=5):
    rows = (
        db.session.query(
            func.coalesce(Category.name, "Uncategorized").label("name"),
            func.sum(Expense.amount).label("total"),
        )
        .outerjoin(Category, (Category.id == Expense.category_id) & (Category.user_id == uid))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .limit(limit)
        .all()
    )
    return [{"category": r.name, "amount": float(r.total)} for r in rows]


def _prev_month(year, month):
    if month == 1:
        return year - 1, 12
    return year, month - 1


@bp.get("/monthly")
@jwt_required()
def monthly_review():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    year, month = map(int, ym.split("-"))
    income, expenses = _get_month_totals(uid, year, month)
    savings_rate = round(((income - expenses) / income) * 100, 2) if income > 0 else 0.0

    prev_y, prev_m = _prev_month(year, month)
    prev_income, prev_expenses = _get_month_totals(uid, prev_y, prev_m)

    income_change = round(income - prev_income, 2)
    expense_change = round(expenses - prev_expenses, 2)

    highlights = []
    if income > prev_income:
        highlights.append("Income increased vs previous month")
    elif income < prev_income:
        highlights.append("Income decreased vs previous month")
    if expenses > prev_expenses:
        highlights.append("Spending increased vs previous month")
    elif expenses < prev_expenses:
        highlights.append("Spending decreased vs previous month")
    if savings_rate > 20:
        highlights.append("Great savings rate above 20%")

    review = {
        "month": ym,
        "income": income,
        "expenses": expenses,
        "savings_rate": savings_rate,
        "top_categories": _top_categories(uid, year, month),
        "vs_previous_month": {
            "income_change": income_change,
            "expense_change": expense_change,
        },
        "highlights": highlights,
    }
    logger.info("Monthly review user=%s month=%s", uid, ym)
    return jsonify(review)
