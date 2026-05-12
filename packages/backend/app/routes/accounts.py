from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, FinancialAccount, User

bp = Blueprint("accounts", __name__)

ACCOUNT_TYPES = {
    "CHECKING",
    "SAVINGS",
    "CREDIT_CARD",
    "INVESTMENT",
    "LOAN",
    "CASH",
    "OTHER",
}
LIABILITY_TYPES = {"CREDIT_CARD", "LOAN"}


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.account_type.asc(), FinancialAccount.name.asc())
        .all()
    )
    return jsonify([_account_to_dict(row) for row in rows])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    payload = request.get_json() or {}
    account, error = _account_from_payload(uid, payload, user=user)
    if error:
        return jsonify(error=error), 400
    db.session.add(account)
    db.session.commit()
    return jsonify(_account_to_dict(account)), 201


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = _get_user_account(uid, account_id)
    if not account:
        return jsonify(error="not found"), 404

    payload = request.get_json() or {}
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name
    if "account_type" in payload:
        account_type = _normalize_account_type(payload.get("account_type"))
        if account_type not in ACCOUNT_TYPES:
            return jsonify(error="invalid account_type"), 400
        account.account_type = account_type
    if "balance" in payload:
        balance = _parse_amount(payload.get("balance"))
        if balance is None:
            return jsonify(error="invalid balance"), 400
        account.balance = balance
    if "currency" in payload:
        currency = str(payload.get("currency") or "").upper().strip()
        if not currency:
            return jsonify(error="currency required"), 400
        account.currency = currency[:10]
    if "institution" in payload:
        account.institution = (payload.get("institution") or "").strip() or None
    db.session.commit()
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    account = _get_user_account(uid, account_id)
    if not account:
        return jsonify(error="not found"), 404
    account.active = False
    db.session.commit()
    return jsonify(message="deleted")


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.name.asc())
        .all()
    )
    year, month = map(int, ym.split("-"))
    activity = _monthly_activity(uid, year, month)
    account_payloads = []
    for account in accounts:
        stats = activity.get(
            account.id, {"income": 0.0, "expenses": 0.0, "transaction_count": 0}
        )
        data = _account_to_dict(account)
        data["monthly_income"] = stats["income"]
        data["monthly_expenses"] = stats["expenses"]
        data["monthly_net_flow"] = round(stats["income"] - stats["expenses"], 2)
        data["transaction_count"] = stats["transaction_count"]
        account_payloads.append(data)

    return jsonify(
        {
            "period": {"month": ym},
            "summary": _summary(accounts),
            "accounts": account_payloads,
            "by_type": _by_type(accounts),
            "by_currency": _by_currency(accounts),
            "recent_transactions": _recent_transactions(uid),
        }
    )


def _account_from_payload(uid: int, payload: dict, user: User | None):
    name = str(payload.get("name") or "").strip()
    if not name:
        return None, "name required"

    account_type = _normalize_account_type(payload.get("account_type") or "OTHER")
    if account_type not in ACCOUNT_TYPES:
        return None, "invalid account_type"

    balance = _parse_amount(payload.get("balance", 0))
    if balance is None:
        return None, "invalid balance"

    currency = (
        str(payload.get("currency") or (user.preferred_currency if user else "INR"))
        .upper()
        .strip()
    )
    if not currency:
        return None, "currency required"

    return (
        FinancialAccount(
            user_id=uid,
            name=name,
            account_type=account_type,
            balance=balance,
            currency=currency[:10],
            institution=(payload.get("institution") or "").strip() or None,
        ),
        None,
    )


def _get_user_account(uid: int, account_id: int):
    return (
        db.session.query(FinancialAccount)
        .filter_by(id=account_id, user_id=uid, active=True)
        .first()
    )


def _summary(accounts: list[FinancialAccount]):
    assets = 0.0
    liabilities = 0.0
    for account in accounts:
        amount = float(account.balance or 0)
        if account.account_type in LIABILITY_TYPES:
            liabilities += amount
        else:
            assets += amount
    return {
        "account_count": len(accounts),
        "assets": round(assets, 2),
        "liabilities": round(liabilities, 2),
        "net_worth": round(assets - liabilities, 2),
    }


def _by_type(accounts: list[FinancialAccount]):
    grouped: dict[str, dict] = {}
    for account in accounts:
        item = grouped.setdefault(
            account.account_type,
            {"account_type": account.account_type, "count": 0, "balance": 0.0},
        )
        item["count"] += 1
        item["balance"] += float(account.balance or 0)
    return [
        {**item, "balance": round(item["balance"], 2)}
        for item in sorted(grouped.values(), key=lambda row: row["account_type"])
    ]


def _by_currency(accounts: list[FinancialAccount]):
    grouped: dict[str, dict] = {}
    for account in accounts:
        item = grouped.setdefault(
            account.currency,
            {"currency": account.currency, "assets": 0.0, "liabilities": 0.0},
        )
        if account.account_type in LIABILITY_TYPES:
            item["liabilities"] += float(account.balance or 0)
        else:
            item["assets"] += float(account.balance or 0)
    return [
        {
            **item,
            "assets": round(item["assets"], 2),
            "liabilities": round(item["liabilities"], 2),
            "net_worth": round(item["assets"] - item["liabilities"], 2),
        }
        for item in sorted(grouped.values(), key=lambda row: row["currency"])
    ]


def _monthly_activity(uid: int, year: int, month: int):
    rows = (
        db.session.query(
            Expense.account_id,
            Expense.expense_type,
            func.coalesce(func.sum(Expense.amount), 0).label("amount"),
            func.count(Expense.id).label("count"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.account_id.isnot(None),
            func.extract("year", Expense.spent_at) == year,
            func.extract("month", Expense.spent_at) == month,
        )
        .group_by(Expense.account_id, Expense.expense_type)
        .all()
    )
    activity: dict[int, dict] = {}
    for row in rows:
        item = activity.setdefault(
            row.account_id, {"income": 0.0, "expenses": 0.0, "transaction_count": 0}
        )
        if row.expense_type == "INCOME":
            item["income"] += float(row.amount or 0)
        else:
            item["expenses"] += float(row.amount or 0)
        item["transaction_count"] += int(row.count or 0)
    return activity


def _recent_transactions(uid: int):
    rows = (
        db.session.query(Expense, FinancialAccount)
        .join(FinancialAccount, FinancialAccount.id == Expense.account_id)
        .filter(Expense.user_id == uid, FinancialAccount.active.is_(True))
        .order_by(Expense.spent_at.desc(), Expense.id.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "id": expense.id,
            "account_id": account.id,
            "account_name": account.name,
            "description": expense.notes or "Transaction",
            "amount": float(expense.amount or 0),
            "currency": expense.currency,
            "date": expense.spent_at.isoformat(),
            "type": expense.expense_type,
        }
        for expense, account in rows
    ]


def _account_to_dict(account: FinancialAccount):
    return {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "balance": float(account.balance or 0),
        "currency": account.currency,
        "institution": account.institution,
        "active": account.active,
    }


def _normalize_account_type(raw) -> str:
    return str(raw or "").upper().strip().replace(" ", "_").replace("-", "_")


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _is_valid_month(ym: str) -> bool:
    if len(ym) != 7 or ym[4] != "-":
        return False
    year, month = ym.split("-")
    if not (year.isdigit() and month.isdigit()):
        return False
    return 1 <= int(month) <= 12
