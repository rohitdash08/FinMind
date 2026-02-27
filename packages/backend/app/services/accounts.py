"""Multi-account financial overview service.

Supports linking multiple financial accounts (bank, credit card, cash, investment)
and provides a unified dashboard view across all accounts.
"""

from datetime import datetime, date, timedelta
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category


class AccountType:
    BANK = "bank"
    CREDIT_CARD = "credit_card"
    CASH = "cash"
    INVESTMENT = "investment"
    SAVINGS = "savings"

    ALL = [BANK, CREDIT_CARD, CASH, INVESTMENT, SAVINGS]


class FinancialAccount(db.Model):
    __tablename__ = "financial_accounts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(50), nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    balance = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


def create_account(user_id: int, name: str, account_type: str,
                   currency: str = "INR", balance: float = 0) -> dict:
    if account_type not in AccountType.ALL:
        raise ValueError(f"Invalid account type. Must be one of: {AccountType.ALL}")

    account = FinancialAccount(
        user_id=user_id,
        name=name,
        account_type=account_type,
        currency=currency,
        balance=balance,
    )
    db.session.add(account)
    db.session.commit()
    return _serialize(account)


def get_accounts(user_id: int, active_only: bool = True) -> list[dict]:
    q = FinancialAccount.query.filter_by(user_id=user_id)
    if active_only:
        q = q.filter_by(is_active=True)
    return [_serialize(a) for a in q.order_by(FinancialAccount.name).all()]


def get_account(user_id: int, account_id: int) -> dict | None:
    a = FinancialAccount.query.filter_by(id=account_id, user_id=user_id).first()
    return _serialize(a) if a else None


def update_account(user_id: int, account_id: int, **kwargs) -> dict | None:
    a = FinancialAccount.query.filter_by(id=account_id, user_id=user_id).first()
    if not a:
        return None
    for key in ("name", "account_type", "currency", "balance", "is_active"):
        if key in kwargs:
            if key == "account_type" and kwargs[key] not in AccountType.ALL:
                raise ValueError(f"Invalid account type. Must be one of: {AccountType.ALL}")
            setattr(a, key, kwargs[key])
    db.session.commit()
    return _serialize(a)


def delete_account(user_id: int, account_id: int) -> bool:
    a = FinancialAccount.query.filter_by(id=account_id, user_id=user_id).first()
    if not a:
        return False
    db.session.delete(a)
    db.session.commit()
    return True


def overview(user_id: int) -> dict:
    """Unified financial overview across all active accounts."""
    accounts = FinancialAccount.query.filter_by(user_id=user_id, is_active=True).all()

    total_balance = sum(float(a.balance) for a in accounts)
    by_type = {}
    for a in accounts:
        by_type.setdefault(a.account_type, {"count": 0, "total": 0})
        by_type[a.account_type]["count"] += 1
        by_type[a.account_type]["total"] += float(a.balance)

    by_currency = {}
    for a in accounts:
        by_currency.setdefault(a.currency, 0)
        by_currency[a.currency] += float(a.balance)

    return {
        "total_accounts": len(accounts),
        "total_balance": round(total_balance, 2),
        "by_type": {k: {"count": v["count"], "total": round(v["total"], 2)} for k, v in by_type.items()},
        "by_currency": {k: round(v, 2) for k, v in by_currency.items()},
        "accounts": [_serialize(a) for a in accounts],
    }


def _serialize(a: FinancialAccount) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "balance": float(a.balance),
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }
