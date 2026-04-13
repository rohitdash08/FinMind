from datetime import date
from sqlalchemy import extract, func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Account, Bill, Expense, Category
from ..services.cache import (
    cache_get,
    cache_set,
    dashboard_summary_key,
    dashboard_overview_key,
)

bp = Blueprint("dashboard", __name__)


@bp.get("/summary")
@jwt_required()
def dashboard_summary():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    account_id = request.args.get("account_id")
    if account_id is not None:
        try:
            account_id = int(account_id)
        except ValueError:
            return jsonify(error="invalid account_id"), 400
        # Verify ownership
        account = db.session.get(Account, account_id)
        if not account or account.user_id != uid or not account.is_active:
            return jsonify(error="account not found"), 404

    cache_suffix = f":{account_id}" if account_id else ""
    key = dashboard_summary_key(uid, ym) + cache_suffix
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
        "errors": [],
    }
    if account_id:
        payload["account_id"] = account_id

    year, month = map(int, ym.split("-"))
    today = date.today()

    try:
        income_q = db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        expenses_q = db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        if account_id:
            income_q = income_q.filter(Expense.account_id == account_id)
            expenses_q = expenses_q.filter(Expense.account_id == account_id)

        income = income_q.scalar()
        expenses = expenses_q.scalar()
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
        recent_q = (
            db.session.query(Expense)
            .filter(Expense.user_id == uid)
        )
        if account_id:
            recent_q = recent_q.filter(Expense.account_id == account_id)
        rows = (
            recent_q.order_by(Expense.spent_at.desc(), Expense.id.desc())
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
                "category_id": e.category_id,
                "currency": e.currency,
                "account_id": e.account_id,
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
        cat_q = (
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
        )
        if account_id:
            cat_q = cat_q.filter(Expense.account_id == account_id)

        category_rows = (
            cat_q.group_by(Expense.category_id, Category.name)
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


@bp.get("/overview")
@jwt_required()
def dashboard_overview():
    """Aggregated view across all accounts."""
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    key = dashboard_overview_key(uid, ym)
    cached = cache_get(key)
    if cached:
        return jsonify(cached)

    year, month = map(int, ym.split("-"))

    # All active accounts
    accounts = (
        db.session.query(Account)
        .filter_by(user_id=uid, is_active=True)
        .order_by(Account.is_default.desc(), Account.name)
        .all()
    )

    total_balance = sum(float(a.balance) for a in accounts)

    # Per-account monthly summaries
    account_summaries = []
    for acct in accounts:
        income = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
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
                Expense.account_id == acct.id,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar()
        )
        account_summaries.append(
            {
                "id": acct.id,
                "name": acct.name,
                "account_type": acct.account_type,
                "balance": float(acct.balance),
                "currency": acct.currency,
                "is_default": acct.is_default,
                "monthly_income": float(income or 0),
                "monthly_expenses": float(expenses or 0),
                "net_flow": round(float(income or 0) - float(expenses or 0), 2),
            }
        )

    # Aggregated totals (all expenses including unassigned)
    agg_income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    agg_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )

    payload = {
        "period": {"month": ym},
        "total_balance": total_balance,
        "accounts_count": len(accounts),
        "aggregate": {
            "monthly_income": float(agg_income or 0),
            "monthly_expenses": float(agg_expenses or 0),
            "net_flow": round(float(agg_income or 0) - float(agg_expenses or 0), 2),
        },
        "accounts": account_summaries,
    }

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
