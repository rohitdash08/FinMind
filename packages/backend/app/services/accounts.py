"""Multi-account financial overview service."""

from datetime import datetime

from ..extensions import db
from ..models import FinancialAccount, AccountType, AccountTransaction

import logging

logger = logging.getLogger("finmind.accounts")


def create_account(
    user_id, name, account_type="checking", institution=None, balance=0, currency="INR"
):
    """Create a new financial account."""
    acct = FinancialAccount(
        user_id=user_id,
        name=name,
        account_type=AccountType(account_type),
        institution=institution,
        balance=balance,
        currency=currency,
    )
    db.session.add(acct)
    db.session.commit()
    return _serialize_account(acct)


def get_account(account_id, user_id):
    """Get a single account with recent transactions."""
    acct = FinancialAccount.query.filter_by(
        id=account_id, user_id=user_id
    ).first_or_404()
    transactions = (
        AccountTransaction.query.filter_by(account_id=account_id)
        .order_by(AccountTransaction.transaction_date.desc())
        .limit(20)
        .all()
    )
    result = _serialize_account(acct)
    result["recent_transactions"] = [_serialize_transaction(t) for t in transactions]
    return result


def list_accounts(user_id, active_only=True):
    """List all accounts for a user."""
    q = FinancialAccount.query.filter_by(user_id=user_id)
    if active_only:
        q = q.filter_by(is_active=True)
    accts = q.order_by(FinancialAccount.name).all()
    return [_serialize_account(a) for a in accts]


def get_overview(user_id):
    """Multi-account dashboard overview.

    Returns total balance, per-type breakdown, and account count.
    """
    accounts = FinancialAccount.query.filter_by(user_id=user_id, is_active=True).all()

    total_balance = sum(float(a.balance) for a in accounts)
    by_type = {}
    for a in accounts:
        atype = (
            a.account_type.value
            if hasattr(a.account_type, "value")
            else str(a.account_type)
        )
        if atype not in by_type:
            by_type[atype] = {"count": 0, "balance": 0.0}
        by_type[atype]["count"] += 1
        by_type[atype]["balance"] += float(a.balance)

    return {
        "total_balance": total_balance,
        "accounts_count": len(accounts),
        "by_type": by_type,
    }


def update_account(account_id, user_id, **kwargs):
    """Update account details."""
    acct = FinancialAccount.query.filter_by(
        id=account_id, user_id=user_id
    ).first_or_404()

    allowed = {"name", "institution", "balance", "currency"}
    for key in allowed:
        if key in kwargs and kwargs[key] is not None:
            setattr(acct, key, kwargs[key])

    if "account_type" in kwargs and kwargs["account_type"]:
        acct.account_type = AccountType(kwargs["account_type"])

    db.session.commit()
    return _serialize_account(acct)


def deactivate_account(account_id, user_id):
    """Soft-delete an account by deactivating it."""
    acct = FinancialAccount.query.filter_by(
        id=account_id, user_id=user_id
    ).first_or_404()
    acct.is_active = False
    db.session.commit()
    return _serialize_account(acct)


def add_transaction(
    account_id, user_id, amount, description=None, category=None, transaction_date=None
):
    """Add a transaction to an account."""
    acct = FinancialAccount.query.filter_by(
        id=account_id, user_id=user_id
    ).first_or_404()

    txn = AccountTransaction(
        account_id=account_id,
        user_id=user_id,
        amount=amount,
        description=description,
        category=category,
        transaction_date=transaction_date or datetime.utcnow(),
    )
    db.session.add(txn)

    # Update account balance
    acct.balance = float(acct.balance) + float(amount)

    db.session.commit()
    return _serialize_transaction(txn)


def list_transactions(account_id, user_id, limit=20):
    """List transactions for an account."""
    FinancialAccount.query.filter_by(id=account_id, user_id=user_id).first_or_404()

    txns = (
        AccountTransaction.query.filter_by(account_id=account_id)
        .order_by(AccountTransaction.transaction_date.desc())
        .limit(limit)
        .all()
    )
    return [_serialize_transaction(t) for t in txns]


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _serialize_account(acct):
    return {
        "id": acct.id,
        "name": acct.name,
        "account_type": (
            acct.account_type.value
            if hasattr(acct.account_type, "value")
            else str(acct.account_type)
        ),
        "institution": acct.institution,
        "balance": float(acct.balance),
        "currency": acct.currency,
        "is_active": acct.is_active,
        "created_at": acct.created_at.isoformat(),
    }


def _serialize_transaction(txn):
    return {
        "id": txn.id,
        "account_id": txn.account_id,
        "amount": float(txn.amount),
        "description": txn.description,
        "category": txn.category,
        "transaction_date": txn.transaction_date.isoformat(),
    }
