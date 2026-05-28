"""Multi-account financial overview service for FinMind.

Features:
- Account CRUD with type validation
- Balance aggregation across accounts
- Net worth calculation
- Transfer between accounts
- Per-account spending breakdown
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from ..extensions import db
from ..models_accounts import Account, AccountTransfer

logger = logging.getLogger("finmind.accounts")


def create_account(user_id: int, name: str, account_type: str, **kwargs) -> Account:
    """Create a new financial account."""
    if account_type not in Account.ACCOUNT_TYPES:
        raise ValueError(f"Invalid account type: {account_type}")

    account = Account(
        user_id=user_id,
        name=name,
        account_type=account_type,
        currency=kwargs.get("currency", "USD"),
        balance=kwargs.get("balance", 0.0),
        credit_limit=kwargs.get("credit_limit"),
        interest_rate=kwargs.get("interest_rate"),
        color=kwargs.get("color"),
        icon=kwargs.get("icon"),
        institution=kwargs.get("institution"),
    )
    db.session.add(account)
    db.session.commit()
    logger.info("Created account %s (%s) for user %d", name, account_type, user_id)
    return account


def get_user_accounts(user_id: int, active_only: bool = True) -> list[Account]:
    """Get all accounts for a user."""
    query = Account.query.filter_by(user_id=user_id)
    if active_only:
        query = query.filter_by(is_active=True)
    return query.order_by(Account.account_type, Account.name).all()


def get_account_summary(user_id: int) -> dict:
    """Get financial overview across all accounts.

    Returns:
        dict with total_balance, net_worth, per_type_totals, accounts list
    """
    accounts = get_user_accounts(user_id)

    total_balance = 0.0
    type_totals = {}
    currency_totals = {}

    for acc in accounts:
        total_balance += acc.balance

        at = acc.account_type
        type_totals.setdefault(at, {"balance": 0.0, "count": 0, "available": 0.0})
        type_totals[at]["balance"] += acc.balance
        type_totals[at]["count"] += 1
        type_totals[at]["available"] += acc.available_balance()

        curr = acc.currency
        currency_totals.setdefault(curr, 0.0)
        currency_totals[curr] += acc.balance

    # Net worth: assets - liabilities
    assets = sum(t["balance"] for t in type_totals.values() if t["balance"] > 0) if type_totals else 0
    liabilities = abs(sum(t["balance"] for t in type_totals.values() if t["balance"] < 0)) if type_totals else 0

    return {
        "total_balance": total_balance,
        "net_worth": assets - liabilities,
        "assets": assets,
        "liabilities": liabilities,
        "type_totals": type_totals,
        "currency_totals": currency_totals,
        "account_count": len(accounts),
        "accounts": [a.to_dict() for a in accounts],
    }


def transfer_between_accounts(user_id: int, from_id: int, to_id: int, amount: float, note: str = None) -> AccountTransfer:
    """Transfer money between two accounts."""
    if amount <= 0:
        raise ValueError("Transfer amount must be positive")

    from_acc = Account.query.filter_by(id=from_id, user_id=user_id).first()
    to_acc = Account.query.filter_by(id=to_id, user_id=user_id).first()

    if not from_acc:
        raise ValueError("Source account not found")
    if not to_acc:
        raise ValueError("Destination account not found")
    if from_acc.id == to_acc.id:
        raise ValueError("Cannot transfer to the same account")

    # Update balances
    from_acc.balance -= amount
    to_acc.balance += amount

    # Record transfer
    transfer = AccountTransfer(
        user_id=user_id,
        from_account_id=from_id,
        to_account_id=to_id,
        amount=amount,
        currency=from_acc.currency,
        note=note,
    )
    db.session.add(transfer)
    db.session.commit()

    logger.info("Transferred %.2f from account %d to %d", amount, from_id, to_id)
    return transfer


def update_account_balance(account_id: int, user_id: int, new_balance: float) -> Account:
    """Update an account balance directly."""
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        raise ValueError("Account not found")
    account.balance = new_balance
    account.last_synced = datetime.now(timezone.utc)
    db.session.commit()
    return account
