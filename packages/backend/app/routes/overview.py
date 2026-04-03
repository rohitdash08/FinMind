from datetime import date
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, case

from ..extensions import db
from ..models import Expense, Bill, User

bp = Blueprint("overview", __name__)


@bp.get("")
@jwt_required()
def financial_overview():
    """Multi-account financial overview aggregated across all data."""
    uid = int(get_jwt_identity())
    user = db.session.query(User).get(uid)
    if not user:
        return jsonify(error="user not found"), 404
    preferred = user.preferred_currency or "INR"

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

    # Monthly trend (last 6 months) - single query with GROUP BY
    try:
        from dateutil.relativedelta import relativedelta

        six_months_ago = (date.today() - relativedelta(months=5)).replace(day=1)
        month_rows = (
            db.session.query(
                func.strftime("%Y-%m", Expense.spent_at).label("month"),
                func.coalesce(
                    func.sum(
                        case(
                            (Expense.expense_type == "INCOME", Expense.amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("income"),
                func.coalesce(
                    func.sum(
                        case(
                            (Expense.expense_type != "INCOME", Expense.amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("expenses"),
            )
            .filter(Expense.user_id == uid, Expense.spent_at >= six_months_ago)
            .group_by("month")
            .order_by("month")
            .all()
        )
        monthly = [
            {
                "month": r.month,
                "income": float(r.income),
                "expenses": float(r.expenses),
                "net": float(r.income - r.expenses),
            }
            for r in month_rows
        ]
    except Exception:
        monthly = []
        errors.append("monthly_trend_unavailable")

    # Net worth - by currency only, no cross-currency sum
    all_currencies = set(list(income_by_currency.keys()) + list(expenses_by_currency.keys()))
    net_worth_by_currency = {}
    for cur in all_currencies:
        inc = income_by_currency.get(cur, 0)
        exp = expenses_by_currency.get(cur, 0)
        net_worth_by_currency[cur] = round(inc - exp, 2)

    return jsonify(
        {
            "net_worth": {
                "by_currency": net_worth_by_currency,
                "preferred_currency": preferred,
                "preferred_net_worth": net_worth_by_currency.get(preferred, 0),
            },
            "income": income_by_currency,
            "expenses": expenses_by_currency,
            "upcoming_bills": bills_by_currency,
            "monthly_trend": monthly,
            "currency_summary": {
                "currencies": list(all_currencies),
                "preferred": preferred,
            },
            "errors": errors,
        }
    )
