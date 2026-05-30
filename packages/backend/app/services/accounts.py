"""Multi-account financial overview service (issue #132).

Public API
----------
create_account(uid, data)             -> (FinancialAccount, error)
get_accounts(uid)                     -> list[FinancialAccount]
get_account(uid, account_id)          -> FinancialAccount | None
update_account(uid, account_id, data) -> (FinancialAccount | None, error)
delete_account(uid, account_id)       -> bool
get_overview(uid)                     -> dict
account_to_dict(acc)                  -> dict
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..extensions import db
from ..models import AccountType, FinancialAccount

logger = logging.getLogger("finmind.accounts")

_ASSET_TYPES = {AccountType.CHECKING.value, AccountType.SAVINGS.value,
                AccountType.INVESTMENT.value, AccountType.CASH.value, AccountType.OTHER.value}
_LIABILITY_TYPES = {AccountType.CREDIT.value}


def _parse_balance(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def account_to_dict(acc: FinancialAccount) -> dict:
    return {
        "id": acc.id,
        "name": acc.name,
        "account_type": acc.account_type,
        "balance": float(acc.balance),
        "currency": acc.currency,
        "institution": acc.institution,
        "is_default": acc.is_default,
        "notes": acc.notes,
        "created_at": acc.created_at.isoformat(),
        "updated_at": acc.updated_at.isoformat(),
    }


def create_account(uid: int, data: dict) -> tuple[FinancialAccount | None, str | None]:
    name = (data.get("name") or "").strip()
    if not name:
        return None, "name required"

    acc_type = str(data.get("account_type") or AccountType.CHECKING.value).upper()
    valid_types = {e.value for e in AccountType}
    if acc_type not in valid_types:
        return None, f"account_type must be one of {sorted(valid_types)}"

    balance = _parse_balance(data.get("balance", 0))
    if balance is None:
        return None, "balance must be a number"

    from ..models import User
    user = db.session.get(User, uid)
    currency = data.get("currency") or (user.preferred_currency if user else "INR")

    # If this is the first account or explicitly set as default, mark it
    existing_count = db.session.query(FinancialAccount).filter_by(user_id=uid).count()
    is_default = bool(data.get("is_default", existing_count == 0))

    if is_default:
        # Clear existing default
        db.session.query(FinancialAccount).filter_by(
            user_id=uid, is_default=True
        ).update({"is_default": False})

    acc = FinancialAccount(
        user_id=uid,
        name=name,
        account_type=acc_type,
        balance=balance,
        currency=currency,
        institution=(data.get("institution") or "").strip() or None,
        is_default=is_default,
        notes=(data.get("notes") or "").strip() or None,
    )
    db.session.add(acc)
    db.session.commit()
    logger.info("Created account id=%s user=%s type=%s", acc.id, uid, acc_type)
    return acc, None


def get_accounts(uid: int) -> list[FinancialAccount]:
    return (
        db.session.query(FinancialAccount)
        .filter_by(user_id=uid)
        .order_by(FinancialAccount.is_default.desc(), FinancialAccount.created_at)
        .all()
    )


def get_account(uid: int, account_id: int) -> FinancialAccount | None:
    return db.session.query(FinancialAccount).filter_by(
        id=account_id, user_id=uid
    ).first()


def update_account(
    uid: int, account_id: int, data: dict
) -> tuple[FinancialAccount | None, str | None]:
    acc = get_account(uid, account_id)
    if not acc:
        return None, "not found"

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return None, "name must not be empty"
        acc.name = name

    if "account_type" in data:
        t = str(data["account_type"] or "").upper()
        valid = {e.value for e in AccountType}
        if t not in valid:
            return None, f"account_type must be one of {sorted(valid)}"
        acc.account_type = t

    if "balance" in data:
        bal = _parse_balance(data["balance"])
        if bal is None:
            return None, "balance must be a number"
        acc.balance = bal

    if "currency" in data and data["currency"]:
        acc.currency = str(data["currency"]).upper()

    if "institution" in data:
        acc.institution = (data["institution"] or "").strip() or None

    if "notes" in data:
        acc.notes = (data["notes"] or "").strip() or None

    if data.get("is_default"):
        db.session.query(FinancialAccount).filter_by(
            user_id=uid, is_default=True
        ).update({"is_default": False})
        acc.is_default = True

    acc.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Updated account id=%s user=%s", acc.id, uid)
    return acc, None


def delete_account(uid: int, account_id: int) -> bool:
    acc = get_account(uid, account_id)
    if not acc:
        return False
    db.session.delete(acc)
    db.session.commit()
    logger.info("Deleted account id=%s user=%s", account_id, uid)
    return True


def get_overview(uid: int) -> dict:
    """Aggregate all accounts into a financial overview with net worth."""
    accounts = get_accounts(uid)

    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    by_type: dict[str, float] = {}

    for acc in accounts:
        t = acc.account_type
        bal = acc.balance or Decimal("0")
        by_type[t] = by_type.get(t, 0.0) + float(bal)
        if t in _LIABILITY_TYPES:
            total_liabilities += bal
        else:
            total_assets += bal

    net_worth = total_assets - total_liabilities

    return {
        "account_count": len(accounts),
        "total_assets": float(total_assets),
        "total_liabilities": float(total_liabilities),
        "net_worth": float(net_worth),
        "by_type": by_type,
        "accounts": [account_to_dict(a) for a in accounts],
    }
