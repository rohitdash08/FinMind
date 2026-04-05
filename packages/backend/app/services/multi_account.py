"""
Multi-account financial overview dashboard (issue #132 — $200 bounty).
Allows users to create named financial accounts (checking, savings, credit)
and view a unified overview across all of them.
"""
import logging
from datetime import date
from sqlalchemy import func
from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.accounts")


class FinancialAccount(db.Model):
    __tablename__ = "financial_accounts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(50), default="checking", nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    balance = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    institution = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=date.today, nullable=False)


VALID_TYPES = {"checking", "savings", "credit", "investment", "cash", "loan"}


def create_account(user_id: int, name: str, account_type: str = "checking",
                   currency: str = "INR", balance: float = 0,
                   institution: str = None) -> FinancialAccount:
    if account_type not in VALID_TYPES:
        raise ValueError(f"Invalid account_type. Must be one of: {VALID_TYPES}")
    acct = FinancialAccount(user_id=user_id, name=name, account_type=account_type,
                            currency=currency, balance=balance, institution=institution)
    db.session.add(acct)
    db.session.commit()
    return acct


def update_balance(account_id: int, new_balance: float) -> FinancialAccount:
    acct = db.session.get(FinancialAccount, account_id)
    if not acct:
        raise ValueError(f"Account {account_id} not found")
    acct.balance = new_balance
    db.session.commit()
    return acct


def get_overview(user_id: int) -> dict:
    """Unified overview across all active accounts."""
    accounts = (db.session.query(FinancialAccount)
                .filter_by(user_id=user_id, is_active=True)
                .order_by(FinancialAccount.id).all())

    total_assets = sum(float(a.balance) for a in accounts
                       if a.account_type not in ("credit", "loan"))
    total_liabilities = sum(float(a.balance) for a in accounts
                            if a.account_type in ("credit", "loan"))
    net_worth = total_assets - total_liabilities

    by_type = {}
    for a in accounts:
        by_type.setdefault(a.account_type, []).append(_acct_dict(a))

    return {
        "net_worth": round(net_worth, 2),
        "total_assets": round(total_assets, 2),
        "total_liabilities": round(total_liabilities, 2),
        "account_count": len(accounts),
        "by_type": by_type,
        "accounts": [_acct_dict(a) for a in accounts],
    }


def _acct_dict(a: FinancialAccount) -> dict:
    return {
        "id": a.id, "name": a.name, "type": a.account_type,
        "balance": float(a.balance), "currency": a.currency,
        "institution": a.institution, "is_active": a.is_active,
    }
