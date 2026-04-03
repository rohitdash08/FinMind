from datetime import date
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, Bill, User

bp = Blueprint("overview", __name__)

ALLOWED_CURRENCIES = {"EUR", "USD", "INR", "GBP"}


@bp.get("")
@jwt_required()
def financial_overview():
    """Multi-account financial overview aggregated across all data."""
    uid = int(get_jwt_identity())
    user = db.session.query(User).get(uid)
    preferred = user.preferred_currency if user else "INR"

    errors = []

    # Income by currency
    try:
        income_rows = (
            db.session.query(
                Expense.currency,
                func.coalesce(func.sum(Expense.amount), 0).label("total"),
            )
            .filter(Expense.user_id == uid, Expense.expense_type == "INCOME")
            .group_by(Expense.currency)
            .all()
        )
        income_by_currency = {r.currency: float(r.total) for r in income_rows}
    except Exception:
        income_by_currency = {}
        errors.append("income_unavailable")

    # Expenses by currency
    try:
        expense_rows = (
            db.session.query(
                Expense.currency,
                func.coalesce(func.sum(Expense.amount), 0).label("total"),
            )
            .filter(Expense.user_id == uid, Expense.expense_type != "INCOME")
            .group_by(Expense.currency)
            .all()
        )
        expenses_by_currency = {r.currency: float(r.total) for r in expense_rows}
    except Exception:
        expenses_by_currency = {}
        errors.append("expenses_unavailable")

    # Bills by currency
    try:
        bill_rows = (
            db.session.query(
                Bill.currency,
                func.coalesce(func.sum(Bill.amount), 0).label("total"),
                func.count(Bill.id).label("count"),
            )
            .filter(Bill.user_id == uid, Bill.active.is_(True))
            .group_by(Bill.currency)
            .all()
        )
        bills_by_currency = {
            r.currency: {"total": float(r.total), "count": r.count} for r in bill_rows
        }
    except Exception:
        bills_by_currency = {}
        errors.append("bills_unavailable")

    # Monthly trend (last 6 months)
    try:
        six_months_ago = date.today().replace(day=1)
        from dateutil.relativedelta import relativedelta

        monthly = []
        for i in range(6):
            month_date = six_months_ago - relativedelta(months=i)
            inc = (
                db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                .filter(
                    Expense.user_id == uid,
                    Expense.expense_type == "INCOME",
                    func.strftime("%Y-%m", Expense.spent_at) == month_date.strftime("%Y-%m"),
                )
                .scalar()
            )
            exp = (
                db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                .filter(
                    Expense.user_id == uid,
                    Expense.expense_type != "INCOME",
                    func.strftime("%Y-%m", Expense.spent_at) == month_date.strftime("%Y-%m"),
                )
                .scalar()
            )
            monthly.append(
                {
                    "month": month_date.strftime("%Y-%m"),
                    "income": float(inc or 0),
                    "expenses": float(exp or 0),
                    "net": float((inc or 0) - (exp or 0)),
                }
            )
    except Exception:
        monthly = []
        errors.append("monthly_trend_unavailable")

    # Net worth calculation
    all_currencies = set(list(income_by_currency.keys()) + list(expenses_by_currency.keys()))
    net_worth_by_currency = {}
    for cur in all_currencies:
        inc = income_by_currency.get(cur, 0)
        exp = expenses_by_currency.get(cur, 0)
        net_worth_by_currency[cur] = round(inc - exp, 2)

    total_net_worth = sum(net_worth_by_currency.values())

    return jsonify(
        {
            "net_worth": {
                "by_currency": net_worth_by_currency,
                "total": round(total_net_worth, 2),
                "preferred_currency": preferred,
            },
            "income": income_by_currency,
            "expenses": expenses_by_currency,
            "upcoming_bills": bills_by_currency,
            "monthly_trend": sorted(monthly, key=lambda x: x["month"]),
            "currency_summary": {
                "currencies": list(all_currencies),
                "preferred": preferred,
            },
            "errors": errors,
        }
    )
