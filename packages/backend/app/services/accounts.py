"""Financial accounts management service."""

from ..extensions import db
from ..models import FinancialAccount


VALID_ACCOUNT_TYPES = {"checking", "savings", "credit", "cash", "investment"}


def create_account(user_id, name, account_type, currency="INR", balance=0, color=None):
    name = (name or "").strip()
    account_type = (account_type or "").strip().lower()

    if not name:
        return None, "Name is required"
    if account_type not in VALID_ACCOUNT_TYPES:
        return (
            None,
            f"Invalid account type. Must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}",
        )

    account = FinancialAccount(
        user_id=user_id,
        name=name,
        account_type=account_type,
        currency=currency,
        balance=balance,
        color=color,
    )
    db.session.add(account)
    db.session.commit()
    return account, None


def get_accounts(user_id, active_only=True):
    query = FinancialAccount.query.filter_by(user_id=user_id)
    if active_only:
        query = query.filter_by(is_active=True)
    return query.order_by(FinancialAccount.name).all()


def get_account(account_id, user_id):
    return FinancialAccount.query.filter_by(id=account_id, user_id=user_id).first()


def update_account(account_id, user_id, **kwargs):
    account = get_account(account_id, user_id)
    if not account:
        return None, "Account not found"

    if "account_type" in kwargs:
        at = (kwargs["account_type"] or "").strip().lower()
        if at not in VALID_ACCOUNT_TYPES:
            return (
                None,
                f"Invalid account type. Must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}",
            )
        kwargs["account_type"] = at

    if "name" in kwargs:
        kwargs["name"] = (kwargs["name"] or "").strip()

    for key in ("name", "account_type", "currency", "balance", "is_active", "color"):
        if key in kwargs and kwargs[key] is not None:
            setattr(account, key, kwargs[key])

    db.session.commit()
    return account, None


def delete_account(account_id, user_id):
    account = get_account(account_id, user_id)
    if not account:
        return False
    account.is_active = False
    db.session.commit()
    return True


def get_overview(user_id):
    """Get aggregated overview across all active accounts."""
    accounts = get_accounts(user_id, active_only=True)

    total_balance = sum(float(a.balance) for a in accounts)
    by_type = {}
    for a in accounts:
        by_type.setdefault(a.account_type, {"count": 0, "total": 0})
        by_type[a.account_type]["count"] += 1
        by_type[a.account_type]["total"] += float(a.balance)

    # Net worth: assets minus liabilities.
    # Credit account balances represent amounts owed (stored as positive numbers),
    # so they are subtracted from total assets to compute net worth.
    assets = sum(float(a.balance) for a in accounts if a.account_type != "credit")
    liabilities = sum(float(a.balance) for a in accounts if a.account_type == "credit")

    return {
        "total_balance": round(total_balance, 2),
        "net_worth": round(assets - liabilities, 2),
        "account_count": len(accounts),
        "by_type": {
            k: {"count": v["count"], "total": round(v["total"], 2)}
            for k, v in by_type.items()
        },
        "accounts": [serialize_account(a) for a in accounts],
    }


def serialize_account(account):
    return {
        "id": account.id,
        "name": account.name,
        "account_type": account.account_type,
        "currency": account.currency,
        "balance": float(account.balance),
        "is_active": account.is_active,
        "color": account.color,
        "created_at": account.created_at.isoformat(),
    }
