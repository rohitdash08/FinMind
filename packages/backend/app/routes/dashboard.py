from datetime import date
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import extract, func

from ..extensions import db
from ..models import Bill, Category, Expense, FinancialAccount
from ..services.cache import cache_get, cache_set, dashboard_summary_key

bp = Blueprint("dashboard", __name__)


@bp.get("/summary")
@jwt_required()
def dashboard_summary():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    account_ids, account_error = _parse_account_ids(request.args.get("account_ids"))
    if account_error:
        return jsonify(error=account_error), 400
    if account_ids and not _accounts_belong_to_user(uid, account_ids):
        return jsonify(error="account not found"), 404

    account_filter_key = "all" if not account_ids else ",".join(map(str, account_ids))
    key = dashboard_summary_key(uid, ym, account_filter_key)
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
            "total_balance": 0.0,
            "account_count": 0,
            "selected_account_count": 0,
        },
        "selected_account_ids": account_ids,
        "accounts": [],
        "account_breakdown": [],
        "recent_transactions": [],
        "upcoming_bills": [],
        "category_breakdown": [],
        "errors": [],
    }

    year, month = map(int, ym.split("-"))
    today = date.today()

    try:
        accounts = _active_accounts(uid)
        payload["accounts"] = [
            _account_summary(account, year, month) for account in accounts
        ]
        selected = (
            [a for a in payload["accounts"] if a["id"] in account_ids]
            if account_ids
            else payload["accounts"]
        )
        payload["account_breakdown"] = selected
        payload["summary"]["total_balance"] = round(
            sum(float(a["balance"] or 0) for a in selected), 2
        )
        payload["summary"]["account_count"] = len(accounts)
        payload["summary"]["selected_account_count"] = len(selected)
    except Exception:
        payload["errors"].append("accounts_unavailable")

    try:
        income_query = db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        expense_query = db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        if account_ids:
            income_query = income_query.filter(Expense.account_id.in_(account_ids))
            expense_query = expense_query.filter(Expense.account_id.in_(account_ids))
        income = income_query.scalar()
        expenses = expense_query.scalar()
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
        rows_query = db.session.query(Expense).filter(Expense.user_id == uid)
        if account_ids:
            rows_query = rows_query.filter(Expense.account_id.in_(account_ids))
        rows = (
            rows_query.order_by(Expense.spent_at.desc(), Expense.id.desc())
            .limit(10)
            .all()
        )
        payload["recent_transactions"] = [_transaction_to_dict(e) for e in rows]
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
        category_query = (
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
        if account_ids:
            category_query = category_query.filter(Expense.account_id.in_(account_ids))
        category_rows = (
            category_query.group_by(Expense.category_id, Category.name)
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


def _parse_account_ids(raw: str | None) -> tuple[list[int], str | None]:
    if not raw:
        return [], None
    account_ids: list[int] = []
    for part in raw.split(","):
        value = part.strip()
        if not value:
            continue
        if not value.isdigit():
            return [], "invalid account_ids"
        account_ids.append(int(value))
    return sorted(set(account_ids)), None


def _accounts_belong_to_user(uid: int, account_ids: list[int]) -> bool:
    count = (
        db.session.query(func.count(FinancialAccount.id))
        .filter(FinancialAccount.user_id == uid, FinancialAccount.id.in_(account_ids))
        .scalar()
    )
    return count == len(account_ids)


def _active_accounts(uid: int) -> list[FinancialAccount]:
    return (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.name.asc())
        .all()
    )


def _account_summary(account: FinancialAccount, year: int, month: int) -> dict:
    all_income = _sum_expenses(account.id, "INCOME")
    all_expenses = _sum_expenses(account.id, "EXPENSE")
    monthly_income = _sum_expenses(account.id, "INCOME", year, month)
    monthly_expenses = _sum_expenses(account.id, "EXPENSE", year, month)
    opening = Decimal(str(account.opening_balance or 0))
    balance = opening + all_income - all_expenses
    return {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "institution": account.institution,
        "last_four": account.last_four,
        "currency": account.currency,
        "opening_balance": float(opening),
        "balance": float(balance.quantize(Decimal("0.01"))),
        "monthly_income": float(monthly_income),
        "monthly_expenses": float(monthly_expenses),
        "monthly_net_flow": float(
            (monthly_income - monthly_expenses).quantize(Decimal("0.01"))
        ),
    }


def _sum_expenses(
    account_id: int,
    expense_kind: str,
    year: int | None = None,
    month: int | None = None,
) -> Decimal:
    query = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.account_id == account_id,
    )
    if expense_kind == "INCOME":
        query = query.filter(Expense.expense_type == "INCOME")
    else:
        query = query.filter(Expense.expense_type != "INCOME")
    if year is not None and month is not None:
        query = query.filter(
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
        )
    return Decimal(str(query.scalar() or 0)).quantize(Decimal("0.01"))


def _transaction_to_dict(expense: Expense) -> dict:
    account = (
        db.session.get(FinancialAccount, expense.account_id)
        if expense.account_id
        else None
    )
    return {
        "id": expense.id,
        "description": expense.notes or "Transaction",
        "amount": float(expense.amount),
        "date": expense.spent_at.isoformat(),
        "type": expense.expense_type,
        "category_id": expense.category_id,
        "account_id": expense.account_id,
        "account_name": account.name if account else None,
        "currency": expense.currency,
    }
