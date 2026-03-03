"""Multi-account financial overview service.

Provides CRUD operations for financial accounts and an aggregated
overview across all accounts for a given user.
"""

from __future__ import annotations

from sqlalchemy import func

from ..extensions import db
from ..models import Account, Expense


def create_account(
    uid: int, name: str, account_type: str = "checking", currency: str = "INR"
) -> dict:
    """Create a new financial account for *uid*."""
    acct = Account(
        user_id=uid, name=name, account_type=account_type, currency=currency
    )
    db.session.add(acct)
    db.session.commit()
    return _serialize(acct)


def list_accounts(uid: int) -> list[dict]:
    """Return all accounts for *uid*."""
    accts = (
        db.session.query(Account)
        .filter(Account.user_id == uid)
        .order_by(Account.created_at)
        .all()
    )
    return [_serialize(a) for a in accts]


def get_account(uid: int, account_id: int) -> dict | None:
    acct = db.session.query(Account).filter(
        Account.id == account_id, Account.user_id == uid
    ).first()
    return _serialize(acct) if acct else None


def delete_account(uid: int, account_id: int) -> bool:
    acct = db.session.query(Account).filter(
        Account.id == account_id, Account.user_id == uid
    ).first()
    if not acct:
        return False
    db.session.delete(acct)
    db.session.commit()
    return True


def multi_account_overview(uid: int) -> dict:
    """Aggregate financial overview across all accounts."""
    accts = (
        db.session.query(Account)
        .filter(Account.user_id == uid)
        .all()
    )

    accounts_data = []
    total_balance = 0.0

    for acct in accts:
        income = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
                Expense.expense_type == "INCOME",
            )
            .scalar() or 0
        )
        expenses = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.account_id == acct.id,
                Expense.expense_type != "INCOME",
            )
            .scalar() or 0
        )
        balance = round(income - expenses, 2)
        total_balance += balance

        accounts_data.append({
            "id": acct.id,
            "name": acct.name,
            "type": acct.account_type,
            "currency": acct.currency,
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "balance": balance,
        })

    return {
        "accounts": accounts_data,
        "total_balance": round(total_balance, 2),
        "account_count": len(accounts_data),
    }


def _serialize(acct: Account) -> dict:
    return {
        "id": acct.id,
        "name": acct.name,
        "type": acct.account_type,
        "currency": acct.currency,
        "created_at": acct.created_at.isoformat(),
    }
