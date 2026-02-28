"""Multi-account financial overview service.

Allows users to manage multiple financial accounts and view
an aggregated dashboard across all accounts.
"""

from datetime import datetime, date

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Expense


class FinancialAccount(db.Model):
    __tablename__ = "financial_accounts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(50), nullable=False)  # checking/savings/credit/cash
    currency = db.Column(db.String(10), default="INR", nullable=False)
    balance = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


VALID_TYPES = {"checking", "savings", "credit", "cash", "investment"}


def _acct_to_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "balance": float(a.balance),
        "is_active": a.is_active,
    }


def create_account(user_id: int, name: str, account_type: str,
                    currency: str = "INR", balance: float = 0) -> dict:
    if account_type not in VALID_TYPES:
        raise ValueError(f"Invalid type. Must be one of: {', '.join(VALID_TYPES)}")
    a = FinancialAccount(
        user_id=user_id, name=name, account_type=account_type,
        currency=currency, balance=balance,
    )
    db.session.add(a)
    db.session.commit()
    return _acct_to_dict(a)


def list_accounts(user_id: int) -> list[dict]:
    accts = FinancialAccount.query.filter_by(user_id=user_id).order_by(
        FinancialAccount.created_at.desc()
    ).all()
    return [_acct_to_dict(a) for a in accts]


def get_account(user_id: int, acct_id: int) -> dict | None:
    a = FinancialAccount.query.filter_by(id=acct_id, user_id=user_id).first()
    return _acct_to_dict(a) if a else None


def update_account(user_id: int, acct_id: int, **kwargs) -> dict:
    a = FinancialAccount.query.filter_by(id=acct_id, user_id=user_id).first()
    if not a:
        raise ValueError("Account not found.")
    for field in ("name", "account_type", "currency", "balance", "is_active"):
        if field in kwargs and kwargs[field] is not None:
            if field == "account_type" and kwargs[field] not in VALID_TYPES:
                raise ValueError(f"Invalid type. Must be one of: {', '.join(VALID_TYPES)}")
            setattr(a, field, kwargs[field])
    db.session.commit()
    return _acct_to_dict(a)


def delete_account(user_id: int, acct_id: int) -> bool:
    a = FinancialAccount.query.filter_by(id=acct_id, user_id=user_id).first()
    if not a:
        return False
    db.session.delete(a)
    db.session.commit()
    return True


def overview(user_id: int) -> dict:
    """Aggregated overview across all active accounts."""
    accts = FinancialAccount.query.filter_by(user_id=user_id, is_active=True).all()
    total_balance = sum(float(a.balance) for a in accts)
    by_type = {}
    for a in accts:
        by_type.setdefault(a.account_type, 0)
        by_type[a.account_type] += float(a.balance)
    by_type = {k: round(v, 2) for k, v in by_type.items()}

    return {
        "total_balance": round(total_balance, 2),
        "account_count": len(accts),
        "by_type": by_type,
        "accounts": [_acct_to_dict(a) for a in accts],
    }
