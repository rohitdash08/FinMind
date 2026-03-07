"""Multi-account financial overview routes.

Allows users to register multiple financial accounts (bank, credit card,
cash, investment) and view a unified dashboard across all accounts.
"""

from datetime import datetime, date

from flask import Blueprint, g, jsonify, request

from ..extensions import db
from ..models import AuditLog, Expense, FinancialAccount

accounts_bp = Blueprint("accounts", __name__, url_prefix="/api/accounts")


# ── Account CRUD ────────────────────────────────────────────────


@accounts_bp.route("", methods=["POST"])
def create_account():
    """Create a new financial account."""
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    account_type = (data.get("account_type") or "").strip().upper()

    if not name:
        return jsonify(error="name is required"), 400

    valid_types = {"BANK", "CREDIT_CARD", "CASH", "INVESTMENT", "SAVINGS", "LOAN", "OTHER"}
    if account_type not in valid_types:
        return jsonify(error=f"Invalid account_type. Use one of: {', '.join(sorted(valid_types))}"), 400

    account = FinancialAccount(
        user_id=g.user_id,
        name=name,
        account_type=account_type,
        currency=data.get("currency", "INR"),
        initial_balance=data.get("initial_balance", 0),
        institution=data.get("institution", ""),
        notes=data.get("notes", ""),
        is_active=True,
    )
    db.session.add(account)
    db.session.add(AuditLog(user_id=g.user_id, action=f"account.create:{name}"))
    db.session.commit()

    return jsonify(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        initial_balance=float(account.initial_balance),
    ), 201


@accounts_bp.route("", methods=["GET"])
def list_accounts():
    """List all financial accounts for the current user."""
    active_only = request.args.get("active", "true").lower() == "true"
    query = FinancialAccount.query.filter_by(user_id=g.user_id)
    if active_only:
        query = query.filter_by(is_active=True)
    accounts = query.order_by(FinancialAccount.name).all()

    return jsonify([
        dict(
            id=a.id,
            name=a.name,
            account_type=a.account_type,
            currency=a.currency,
            initial_balance=float(a.initial_balance),
            institution=a.institution,
            is_active=a.is_active,
            created_at=a.created_at.isoformat(),
        )
        for a in accounts
    ])


@accounts_bp.route("/<int:aid>", methods=["GET"])
def get_account(aid):
    """Get account details including current balance."""
    account = FinancialAccount.query.filter_by(id=aid, user_id=g.user_id).first()
    if not account:
        return jsonify(error="Account not found"), 404

    # Calculate current balance: initial + income - expenses
    expenses = Expense.query.filter_by(user_id=g.user_id, account_id=aid).all()
    total_expenses = sum(float(e.amount) for e in expenses if e.expense_type == "EXPENSE")
    total_income = sum(float(e.amount) for e in expenses if e.expense_type == "INCOME")
    current_balance = float(account.initial_balance) + total_income - total_expenses

    return jsonify(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        initial_balance=float(account.initial_balance),
        current_balance=current_balance,
        institution=account.institution,
        notes=account.notes,
        is_active=account.is_active,
    )


@accounts_bp.route("/<int:aid>", methods=["PATCH"])
def update_account(aid):
    """Update account details."""
    account = FinancialAccount.query.filter_by(id=aid, user_id=g.user_id).first()
    if not account:
        return jsonify(error="Account not found"), 404

    data = request.get_json(force=True)
    if "name" in data:
        account.name = data["name"].strip()
    if "institution" in data:
        account.institution = data["institution"]
    if "notes" in data:
        account.notes = data["notes"]
    if "is_active" in data:
        account.is_active = data["is_active"]
    if "initial_balance" in data:
        account.initial_balance = data["initial_balance"]

    db.session.commit()
    return jsonify(id=account.id, name=account.name, is_active=account.is_active)


@accounts_bp.route("/<int:aid>", methods=["DELETE"])
def delete_account(aid):
    """Delete (deactivate) an account."""
    account = FinancialAccount.query.filter_by(id=aid, user_id=g.user_id).first()
    if not account:
        return jsonify(error="Account not found"), 404

    # Soft delete — deactivate instead of hard delete to preserve expense references
    account.is_active = False
    db.session.add(AuditLog(user_id=g.user_id, action=f"account.deactivate:{aid}"))
    db.session.commit()
    return "", 204


# ── Multi-Account Dashboard ────────────────────────────────────


@accounts_bp.route("/overview", methods=["GET"])
def accounts_overview():
    """Unified financial overview across all accounts."""
    accounts = FinancialAccount.query.filter_by(
        user_id=g.user_id, is_active=True
    ).all()

    if not accounts:
        return jsonify(
            total_balance=0,
            accounts=[],
            total_income_this_month=0,
            total_expenses_this_month=0,
        )

    account_ids = [a.id for a in accounts]

    # Get current month expenses
    now = datetime.utcnow()
    month_start = now.replace(day=1).date()

    all_expenses = Expense.query.filter(
        Expense.user_id == g.user_id,
        Expense.account_id.in_(account_ids),
        Expense.spent_at >= month_start,
    ).all()

    # Per-account breakdown
    account_data = []
    total_balance = 0

    for acc in accounts:
        acc_expenses = [e for e in all_expenses if e.account_id == acc.id]
        all_acc_expenses = Expense.query.filter_by(
            user_id=g.user_id, account_id=acc.id
        ).all()

        expenses_sum = sum(float(e.amount) for e in all_acc_expenses if e.expense_type == "EXPENSE")
        income_sum = sum(float(e.amount) for e in all_acc_expenses if e.expense_type == "INCOME")
        current_balance = float(acc.initial_balance) + income_sum - expenses_sum

        month_expenses = sum(float(e.amount) for e in acc_expenses if e.expense_type == "EXPENSE")
        month_income = sum(float(e.amount) for e in acc_expenses if e.expense_type == "INCOME")

        total_balance += current_balance

        account_data.append(dict(
            id=acc.id,
            name=acc.name,
            account_type=acc.account_type,
            currency=acc.currency,
            current_balance=current_balance,
            month_expenses=month_expenses,
            month_income=month_income,
        ))

    total_expenses_month = sum(float(e.amount) for e in all_expenses if e.expense_type == "EXPENSE")
    total_income_month = sum(float(e.amount) for e in all_expenses if e.expense_type == "INCOME")

    return jsonify(
        total_balance=total_balance,
        total_income_this_month=total_income_month,
        total_expenses_this_month=total_expenses_month,
        net_this_month=total_income_month - total_expenses_month,
        account_count=len(accounts),
        accounts=account_data,
    )


@accounts_bp.route("/<int:aid>/transactions", methods=["GET"])
def account_transactions(aid):
    """List transactions for a specific account."""
    account = FinancialAccount.query.filter_by(id=aid, user_id=g.user_id).first()
    if not account:
        return jsonify(error="Account not found"), 404

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)

    query = Expense.query.filter_by(
        user_id=g.user_id, account_id=aid
    ).order_by(Expense.spent_at.desc())

    total = query.count()
    expenses = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        total=total,
        page=page,
        per_page=per_page,
        transactions=[
            dict(
                id=e.id,
                amount=float(e.amount),
                expense_type=e.expense_type,
                notes=e.notes,
                spent_at=e.spent_at.isoformat(),
                category_id=e.category_id,
            )
            for e in expenses
        ],
    )
