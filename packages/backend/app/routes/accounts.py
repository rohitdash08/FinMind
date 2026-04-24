from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import extract, func

from ..extensions import db
from ..models import Expense, FinancialAccount, User
from ..services.cache import cache_delete_patterns

bp = Blueprint("accounts", __name__)

ACCOUNT_TYPES = {"CHECKING", "SAVINGS", "CREDIT", "CASH", "INVESTMENT", "LOAN", "OTHER"}


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    include_inactive = str(request.args.get("include_inactive", "false")).lower() == "true"
    query = db.session.query(FinancialAccount).filter_by(user_id=uid)
    if not include_inactive:
        query = query.filter(FinancialAccount.active.is_(True))
    accounts = query.order_by(FinancialAccount.name.asc()).all()
    return jsonify([_account_to_dict(account) for account in accounts])


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    opening_balance = _parse_amount(data.get("opening_balance", 0))
    if opening_balance is None:
        return jsonify(error="invalid opening_balance"), 400
    account_type = _parse_account_type(data.get("account_type"))
    account = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=account_type,
        currency=str(data.get("currency") or (user.preferred_currency if user else "INR"))[:10],
        opening_balance=opening_balance,
        institution=(str(data.get("institution") or "").strip() or None),
        active=bool(data.get("active", True)),
    )
    db.session.add(account)
    db.session.commit()
    _invalidate_account_cache(uid)
    return jsonify(_account_to_dict(account)), 201


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    account = _get_owned_account(account_id)
    if account is None:
        return jsonify(error="not found"), 404
    return jsonify(_account_to_dict(account, include_summary=True))


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    account = _get_owned_account(account_id)
    if account is None:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        account.name = name
    if "account_type" in data:
        account.account_type = _parse_account_type(data.get("account_type"))
    if "currency" in data:
        account.currency = str(data.get("currency") or account.currency)[:10]
    if "institution" in data:
        account.institution = str(data.get("institution") or "").strip() or None
    if "opening_balance" in data:
        opening_balance = _parse_amount(data.get("opening_balance"))
        if opening_balance is None:
            return jsonify(error="invalid opening_balance"), 400
        account.opening_balance = opening_balance
    if "active" in data:
        account.active = bool(data.get("active"))
    db.session.commit()
    _invalidate_account_cache(uid)
    return jsonify(_account_to_dict(account))


@bp.delete("/<int:account_id>")
@jwt_required()
def deactivate_account(account_id: int):
    uid = int(get_jwt_identity())
    account = _get_owned_account(account_id)
    if account is None:
        return jsonify(error="not found"), 404
    account.active = False
    db.session.commit()
    _invalidate_account_cache(uid)
    return jsonify(message="deactivated")


@bp.get("/overview")
@jwt_required()
def accounts_overview():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or "").strip()
    query = db.session.query(FinancialAccount).filter_by(user_id=uid, active=True)
    accounts = query.order_by(FinancialAccount.name.asc()).all()

    rows = (
        db.session.query(
            Expense.account_id,
            Expense.expense_type,
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
        )
        .filter(Expense.user_id == uid)
    )
    if ym:
        if not _is_valid_month(ym):
            return jsonify(error="invalid month, expected YYYY-MM"), 400
        year, month = map(int, ym.split("-"))
        rows = rows.filter(
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
        )
    rows = rows.group_by(Expense.account_id, Expense.expense_type).all()

    activity = {}
    unassigned = {"income": Decimal("0"), "expenses": Decimal("0")}
    for row in rows:
        bucket = unassigned if row.account_id is None else activity.setdefault(row.account_id, {"income": Decimal("0"), "expenses": Decimal("0")})
        if row.expense_type == "INCOME":
            bucket["income"] += Decimal(row.total_amount or 0)
        else:
            bucket["expenses"] += Decimal(row.total_amount or 0)

    account_payloads = []
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    total_income = Decimal("0")
    total_expenses = Decimal("0")
    for account in accounts:
        bucket = activity.get(account.id, {"income": Decimal("0"), "expenses": Decimal("0")})
        balance = Decimal(account.opening_balance or 0) + bucket["income"] - bucket["expenses"]
        total_income += bucket["income"]
        total_expenses += bucket["expenses"]
        if account.account_type in {"CREDIT", "LOAN"}:
            total_liabilities += balance
        else:
            total_assets += balance
        account_payloads.append(
            {
                **_account_to_dict(account),
                "income": _money(bucket["income"]),
                "expenses": _money(bucket["expenses"]),
                "net_flow": _money(bucket["income"] - bucket["expenses"]),
                "computed_balance": _money(balance),
            }
        )

    total_income += unassigned["income"]
    total_expenses += unassigned["expenses"]
    return jsonify(
        {
            "period": {"month": ym or None},
            "summary": {
                "account_count": len(accounts),
                "total_assets": _money(total_assets),
                "total_liabilities": _money(total_liabilities),
                "net_worth": _money(total_assets - total_liabilities),
                "monthly_income": _money(total_income),
                "monthly_expenses": _money(total_expenses),
                "net_flow": _money(total_income - total_expenses),
            },
            "accounts": account_payloads,
            "unassigned_activity": {
                "income": _money(unassigned["income"]),
                "expenses": _money(unassigned["expenses"]),
                "net_flow": _money(unassigned["income"] - unassigned["expenses"]),
            },
        }
    )


def _get_owned_account(account_id: int) -> FinancialAccount | None:
    uid = int(get_jwt_identity())
    account = db.session.get(FinancialAccount, account_id)
    if not account or account.user_id != uid:
        return None
    return account


def _account_to_dict(account: FinancialAccount, include_summary: bool = False) -> dict:
    payload = {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "currency": account.currency,
        "institution": account.institution,
        "opening_balance": _money(account.opening_balance),
        "active": account.active,
        "created_at": account.created_at.isoformat(),
    }
    if include_summary:
        income, expenses = _account_activity(account.id)
        payload["income"] = _money(income)
        payload["expenses"] = _money(expenses)
        payload["computed_balance"] = _money(Decimal(account.opening_balance or 0) + income - expenses)
    return payload


def _account_activity(account_id: int) -> tuple[Decimal, Decimal]:
    rows = (
        db.session.query(Expense.expense_type, func.coalesce(func.sum(Expense.amount), 0).label("total_amount"))
        .filter(Expense.account_id == account_id)
        .group_by(Expense.expense_type)
        .all()
    )
    income = Decimal("0")
    expenses = Decimal("0")
    for row in rows:
        if row.expense_type == "INCOME":
            income += Decimal(row.total_amount or 0)
        else:
            expenses += Decimal(row.total_amount or 0)
    return income, expenses


def _parse_account_type(raw: str | None) -> str:
    account_type = str(raw or "CHECKING").upper().strip()
    return account_type if account_type in ACCOUNT_TYPES else "OTHER"


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _money(value) -> float:
    return float(Decimal(value or 0).quantize(Decimal("0.01")))


def _is_valid_month(ym: str) -> bool:
    if len(ym) != 7 or ym[4] != "-":
        return False
    year, month = ym.split("-")
    return year.isdigit() and month.isdigit() and 1 <= int(month) <= 12


def _invalidate_account_cache(uid: int) -> None:
    cache_delete_patterns([f"user:{uid}:dashboard_summary:*", f"user:{uid}:accounts:*"])
