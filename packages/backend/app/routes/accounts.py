"""
Routes for managing financial accounts (multi-account dashboard feature).

Endpoints:
  GET    /accounts               – list all active accounts for the current user
  POST   /accounts               – create a new financial account
  GET    /accounts/<id>          – get a specific account
  PATCH  /accounts/<id>          – update a financial account
  DELETE /accounts/<id>          – soft-delete (deactivate) an account
  GET    /accounts/overview      – aggregate multi-account dashboard summary
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import extract, func

from ..extensions import db
from ..models import AccountType, Bill, Expense, FinancialAccount

bp = Blueprint("accounts", __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ACCOUNT_TYPES = {t.value for t in AccountType}


def _account_to_dict(acct: FinancialAccount) -> dict:
    return {
        "id": acct.id,
        "name": acct.name,
        "account_type": acct.account_type.value if acct.account_type else None,
        "balance": float(acct.balance or 0),
        "currency": acct.currency,
        "institution": acct.institution,
        "last_four": acct.last_four,
        "color": acct.color,
        "include_in_overview": acct.include_in_overview,
        "active": acct.active,
        "created_at": acct.created_at.isoformat() if acct.created_at else None,
        "updated_at": acct.updated_at.isoformat() if acct.updated_at else None,
    }


def _parse_decimal(value, field: str):
    """Return (Decimal, None) on success or (None, error_response) on failure."""
    try:
        d = Decimal(str(value))
        return d, None
    except (InvalidOperation, TypeError, ValueError):
        return None, (jsonify(error=f"invalid {field}"), 400)


# ---------------------------------------------------------------------------
# List accounts
# ---------------------------------------------------------------------------


@bp.get("")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    q = db.session.query(FinancialAccount).filter_by(user_id=uid)
    if not include_inactive:
        q = q.filter(FinancialAccount.active.is_(True))
    accounts = q.order_by(FinancialAccount.created_at.asc()).all()
    return jsonify([_account_to_dict(a) for a in accounts])


# ---------------------------------------------------------------------------
# Create account
# ---------------------------------------------------------------------------


@bp.post("")
@jwt_required()
def create_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    acct_type_raw = (data.get("account_type") or "CHECKING").upper()
    if acct_type_raw not in _VALID_ACCOUNT_TYPES:
        return jsonify(
            error=f"account_type must be one of: {', '.join(sorted(_VALID_ACCOUNT_TYPES))}"
        ), 400

    balance_raw = data.get("balance", 0)
    balance, err = _parse_decimal(balance_raw, "balance")
    if err:
        return err

    currency = (data.get("currency") or "INR").upper().strip()
    institution = (data.get("institution") or "").strip() or None
    last_four = (data.get("last_four") or "").strip() or None
    if last_four and (len(last_four) != 4 or not last_four.isdigit()):
        return jsonify(error="last_four must be exactly 4 digits"), 400
    color = (data.get("color") or "").strip() or None
    include_in_overview = bool(data.get("include_in_overview", True))

    acct = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=AccountType(acct_type_raw),
        balance=balance,
        currency=currency,
        institution=institution,
        last_four=last_four,
        color=color,
        include_in_overview=include_in_overview,
    )
    db.session.add(acct)
    db.session.commit()
    return jsonify(_account_to_dict(acct)), 201


# ---------------------------------------------------------------------------
# Get single account
# ---------------------------------------------------------------------------


@bp.get("/<int:account_id>")
@jwt_required()
def get_account(account_id: int):
    uid = int(get_jwt_identity())
    acct = db.session.query(FinancialAccount).filter_by(
        id=account_id, user_id=uid
    ).first()
    if not acct:
        return jsonify(error="account not found"), 404
    return jsonify(_account_to_dict(acct))


# ---------------------------------------------------------------------------
# Update account
# ---------------------------------------------------------------------------


@bp.patch("/<int:account_id>")
@jwt_required()
def update_account(account_id: int):
    uid = int(get_jwt_identity())
    acct = db.session.query(FinancialAccount).filter_by(
        id=account_id, user_id=uid
    ).first()
    if not acct:
        return jsonify(error="account not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name cannot be empty"), 400
        acct.name = name

    if "account_type" in data:
        acct_type_raw = (data["account_type"] or "").upper()
        if acct_type_raw not in _VALID_ACCOUNT_TYPES:
            return jsonify(
                error=f"account_type must be one of: {', '.join(sorted(_VALID_ACCOUNT_TYPES))}"
            ), 400
        acct.account_type = AccountType(acct_type_raw)

    if "balance" in data:
        balance, err = _parse_decimal(data["balance"], "balance")
        if err:
            return err
        acct.balance = balance

    if "currency" in data:
        acct.currency = (data["currency"] or "INR").upper().strip()

    if "institution" in data:
        acct.institution = (data["institution"] or "").strip() or None

    if "last_four" in data:
        last_four = (data["last_four"] or "").strip() or None
        if last_four and (len(last_four) != 4 or not last_four.isdigit()):
            return jsonify(error="last_four must be exactly 4 digits"), 400
        acct.last_four = last_four

    if "color" in data:
        acct.color = (data["color"] or "").strip() or None

    if "include_in_overview" in data:
        acct.include_in_overview = bool(data["include_in_overview"])

    db.session.commit()
    return jsonify(_account_to_dict(acct))


# ---------------------------------------------------------------------------
# Delete (deactivate) account
# ---------------------------------------------------------------------------


@bp.delete("/<int:account_id>")
@jwt_required()
def delete_account(account_id: int):
    uid = int(get_jwt_identity())
    acct = db.session.query(FinancialAccount).filter_by(
        id=account_id, user_id=uid
    ).first()
    if not acct:
        return jsonify(error="account not found"), 404
    acct.active = False
    db.session.commit()
    return jsonify(message="account deactivated"), 200


# ---------------------------------------------------------------------------
# Multi-account overview
# ---------------------------------------------------------------------------


@bp.get("/overview")
@jwt_required()
def multi_account_overview():
    """
    Aggregated financial overview across all active accounts that have
    ``include_in_overview=True``.

    Returns:
      - accounts: list of account details with individual balances
      - totals: net_worth, total_assets, total_liabilities
      - monthly_summary: income / expenses for the requested month
      - upcoming_bills: next-due bills (across all accounts context)
      - category_breakdown: expense breakdown for the requested month
    """
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    year, month = map(int, ym.split("-"))
    today = date.today()

    # --- accounts -----------------------------------------------------------
    accounts = (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid, active=True)
        .order_by(FinancialAccount.created_at.asc())
        .all()
    )

    overview_accounts = [a for a in accounts if a.include_in_overview]

    # Compute totals
    # Liability account types carry negative contribution to net worth
    _LIABILITY_TYPES = {AccountType.CREDIT_CARD, AccountType.LOAN}

    total_assets: float = 0.0
    total_liabilities: float = 0.0
    for acct in overview_accounts:
        bal = float(acct.balance or 0)
        if acct.account_type in _LIABILITY_TYPES:
            # A positive balance on a credit card / loan means money owed → liability
            total_liabilities += abs(bal) if bal > 0 else 0
            # If balance is negative (paid ahead) treat as 0 liability
        else:
            if bal > 0:
                total_assets += bal

    net_worth = round(total_assets - total_liabilities, 2)

    # --- monthly income / expenses ------------------------------------------
    monthly_income: float = 0.0
    monthly_expenses: float = 0.0
    errors = []

    try:
        income_q = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type == "INCOME",
            )
            .scalar()
        )
        expenses_q = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar()
        )
        monthly_income = float(income_q or 0)
        monthly_expenses = float(expenses_q or 0)
    except Exception:
        errors.append("monthly_summary_unavailable")

    # --- upcoming bills -----------------------------------------------------
    upcoming_bills = []
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
        upcoming_bills = [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "currency": b.currency,
                "next_due_date": b.next_due_date.isoformat(),
                "cadence": b.cadence.value,
            }
            for b in bills
        ]
    except Exception:
        errors.append("upcoming_bills_unavailable")

    # --- category breakdown -------------------------------------------------
    category_breakdown = []
    try:
        from ..models import Category

        cat_rows = (
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
        total_cat = sum(float(r.total_amount or 0) for r in cat_rows)
        category_breakdown = [
            {
                "category_id": r.category_id,
                "category_name": r.category_name,
                "amount": float(r.total_amount or 0),
                "share_pct": (
                    round((float(r.total_amount or 0) / total_cat) * 100, 2)
                    if total_cat > 0
                    else 0
                ),
            }
            for r in cat_rows
        ]
    except Exception:
        errors.append("category_breakdown_unavailable")

    return jsonify(
        {
            "period": {"month": ym},
            "accounts": [_account_to_dict(a) for a in accounts],
            "totals": {
                "net_worth": net_worth,
                "total_assets": round(total_assets, 2),
                "total_liabilities": round(total_liabilities, 2),
            },
            "monthly_summary": {
                "income": monthly_income,
                "expenses": monthly_expenses,
                "net_flow": round(monthly_income - monthly_expenses, 2),
            },
            "upcoming_bills": upcoming_bills,
            "category_breakdown": category_breakdown,
            "errors": errors,
        }
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_valid_month(ym: str) -> bool:
    if len(ym) != 7 or ym[4] != "-":
        return False
    year_part, month_part = ym.split("-")
    if not (year_part.isdigit() and month_part.isdigit()):
        return False
    return 1 <= int(month_part) <= 12
