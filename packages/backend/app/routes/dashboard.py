from datetime import date
from sqlalchemy import case, extract, func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Bill, Expense, Category, FinancialAccount
from ..services.cache import cache_get, cache_set, dashboard_summary_key

bp = Blueprint("dashboard", __name__)


@bp.get("/summary")
@jwt_required()
def dashboard_summary():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400
    key = dashboard_summary_key(uid, ym)
    cached = cache_get(key)
    if cached:
        return jsonify(cached)

    payload = {
        "period": {"month": ym},
        "summary": {
            "net_flow": 0.0,
            "monthly_income": 0.0,
            "monthly_expenses": 0.0,
            "upcoming_bills_total": 0.0,
            "upcoming_bills_count": 0,
        },
        "recent_transactions": [],
        "upcoming_bills": [],
        "category_breakdown": [],
        "account_overview": [],
        "errors": [],
    }

    year, month = map(int, ym.split("-"))
    today = date.today()

    try:
        income = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type == "INCOME",
            )
            .scalar()
        )
        expenses = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar()
        )
        payload["summary"]["monthly_income"] = float(income or 0)
        payload["summary"]["monthly_expenses"] = float(expenses or 0)
        payload["summary"]["net_flow"] = round(
            payload["summary"]["monthly_income"]
            - payload["summary"]["monthly_expenses"],
            2,
        )
    except Exception:
        payload["errors"].append("summary_unavailable")

    try:
        rows = (
            db.session.query(Expense)
            .filter(Expense.user_id == uid)
            .order_by(Expense.spent_at.desc(), Expense.id.desc())
            .limit(10)
            .all()
        )
        payload["recent_transactions"] = [
            {
                "id": e.id,
                "description": e.notes or "Transaction",
                "amount": float(e.amount),
                "date": e.spent_at.isoformat(),
                "type": e.expense_type,
                "account_id": e.account_id,
                "category_id": e.category_id,
                "currency": e.currency,
            }
            for e in rows
        ]
    except Exception:
        payload["errors"].append("recent_transactions_unavailable")

    try:
        bills = (
            db.session.query(Bill)
            .filter(
                Bill.user_id == uid,
                Bill.active.is_(True),
                Bill.next_due_date >= today,
            )
            .order_by(Bill.next_due_date.asc())
            .limit(8)
            .all()
        )
        payload["upcoming_bills"] = [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "currency": b.currency,
                "next_due_date": b.next_due_date.isoformat(),
                "cadence": b.cadence.value,
                "channel_email": b.channel_email,
                "channel_whatsapp": b.channel_whatsapp,
            }
            for b in bills
        ]
        payload["summary"]["upcoming_bills_total"] = round(
            sum(float(b.amount) for b in bills), 2
        )
        payload["summary"]["upcoming_bills_count"] = len(bills)
    except Exception:
        payload["errors"].append("upcoming_bills_unavailable")

    try:
        account_rows = (
            db.session.query(
                FinancialAccount,
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
            .outerjoin(
                Expense,
                (Expense.account_id == FinancialAccount.id)
                & (Expense.user_id == uid)
                & (extract("year", Expense.spent_at) == year)
                & (extract("month", Expense.spent_at) == month),
            )
            .filter(FinancialAccount.user_id == uid, FinancialAccount.active.is_(True))
            .group_by(FinancialAccount.id)
            .order_by(FinancialAccount.name)
            .all()
        )
        unassigned_income = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id.is_(None),
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type == "INCOME",
            )
            .scalar()
        )
        unassigned_expenses = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id.is_(None),
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar()
        )
        payload["account_overview"] = [
            _account_row_to_dict(account, income, expenses)
            for account, income, expenses in account_rows
        ]
        if float(unassigned_income or 0) or float(unassigned_expenses or 0):
            payload["account_overview"].append(
                {
                    "account_id": None,
                    "name": "Unassigned",
                    "account_type": "OTHER",
                    "currency": None,
                    "opening_balance": 0.0,
                    "monthly_income": float(unassigned_income or 0),
                    "monthly_expenses": float(unassigned_expenses or 0),
                    "net_flow": round(
                        float(unassigned_income or 0) - float(unassigned_expenses or 0),
                        2,
                    ),
                    "projected_balance": round(
                        float(unassigned_income or 0) - float(unassigned_expenses or 0),
                        2,
                    ),
                }
            )
    except Exception:
        payload["errors"].append("account_overview_unavailable")

    try:
        category_rows = (
            db.session.query(
                Expense.category_id,
                func.coalesce(Category.name, "Uncategorized").label("category_name"),
                func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
            )
            .outerjoin(
                Category,
                (Category.id == Expense.category_id) & (Category.user_id == uid),
            )
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .group_by(Expense.category_id, Category.name)
            .order_by(func.sum(Expense.amount).desc())
            .all()
        )
        total = sum(float(r.total_amount or 0) for r in category_rows)
        payload["category_breakdown"] = [
            {
                "category_id": r.category_id,
                "category_name": r.category_name,
                "amount": float(r.total_amount or 0),
                "share_pct": (
                    round((float(r.total_amount or 0) / total) * 100, 2)
                    if total > 0
                    else 0
                ),
            }
            for r in category_rows
        ]
    except Exception:
        payload["errors"].append("category_breakdown_unavailable")

    cache_set(key, payload, ttl_seconds=300)
    return jsonify(payload)


def _is_valid_month(ym: str) -> bool:
    if len(ym) != 7 or ym[4] != "-":
        return False
    year, month = ym.split("-")
    if not (year.isdigit() and month.isdigit()):
        return False
    m = int(month)
    return 1 <= m <= 12


def _account_row_to_dict(account: FinancialAccount, income, expenses) -> dict:
    income_value = float(income or 0)
    expense_value = float(expenses or 0)
    opening_balance = float(account.opening_balance or 0)
    net_flow = round(income_value - expense_value, 2)
    return {
        "account_id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "currency": account.currency,
        "opening_balance": opening_balance,
        "monthly_income": income_value,
        "monthly_expenses": expense_value,
        "net_flow": net_flow,
        "projected_balance": round(opening_balance + net_flow, 2),
    }
