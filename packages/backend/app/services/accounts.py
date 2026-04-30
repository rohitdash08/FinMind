import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func

from ..extensions import db
from ..models import Account, AccountType, Expense
from .cache import (
    accounts_key,
    account_overview_key,
    cache_delete_patterns,
    cache_get,
    cache_set,
)

logger = logging.getLogger("finmind.accounts")


def create_account(user_id: int, data: dict) -> Account:
    """Create a new account. If this is the user's first account, also create
    a default 'Unassigned' account."""
    existing_count = (
        db.session.query(func.count(Account.id))
        .filter_by(user_id=user_id)
        .scalar()
    )
    if existing_count == 0:
        default = Account(
            user_id=user_id,
            name="Unassigned",
            account_type=AccountType.OTHER.value,
            currency=data.get("currency", "INR"),
            balance=Decimal("0.00"),
            icon="wallet",
            color="#94a3b8",
            is_active=True,
        )
        db.session.add(default)

    account_type = data.get("account_type", AccountType.CHECKING.value)
    if account_type not in {t.value for t in AccountType}:
        account_type = AccountType.OTHER.value

    account = Account(
        user_id=user_id,
        name=data["name"],
        account_type=account_type,
        currency=data.get("currency", "INR"),
        balance=Decimal(str(data.get("balance", 0))).quantize(Decimal("0.01")),
        icon=data.get("icon"),
        color=data.get("color"),
        is_active=True,
    )
    db.session.add(account)
    db.session.commit()
    _invalidate_account_cache(user_id)
    logger.info("Created account id=%s user=%s name=%s", account.id, user_id, account.name)
    return account


def get_accounts(user_id: int) -> list[Account]:
    """Return all active accounts for a user."""
    cached = cache_get(accounts_key(user_id))
    if cached:
        return cached  # 既にシリアライズ済みリスト

    items = (
        db.session.query(Account)
        .filter_by(user_id=user_id, is_active=True)
        .order_by(Account.created_at.asc())
        .all()
    )
    serialized = [account_to_dict(a) for a in items]
    cache_set(accounts_key(user_id), serialized, ttl_seconds=300)
    return serialized


def get_account(user_id: int, account_id: int) -> Account | None:
    """Return a single account if it belongs to the user."""
    account = db.session.get(Account, account_id)
    if not account or account.user_id != user_id:
        return None
    return account


def update_account(user_id: int, account_id: int, data: dict) -> Account | None:
    """Update an existing account."""
    account = get_account(user_id, account_id)
    if not account:
        return None

    if "name" in data:
        account.name = str(data["name"])[:100]
    if "account_type" in data:
        at = data["account_type"]
        if at in {t.value for t in AccountType}:
            account.account_type = at
    if "currency" in data:
        account.currency = str(data["currency"])[:10]
    if "balance" in data:
        account.balance = Decimal(str(data["balance"])).quantize(Decimal("0.01"))
    if "icon" in data:
        account.icon = data["icon"]
    if "color" in data:
        account.color = data["color"]

    account.updated_at = datetime.utcnow()
    db.session.commit()
    _invalidate_account_cache(user_id)
    logger.info("Updated account id=%s user=%s", account_id, user_id)
    return account


def soft_delete_account(user_id: int, account_id: int) -> bool:
    """Soft delete an account by setting is_active=False."""
    account = get_account(user_id, account_id)
    if not account:
        return False

    account.is_active = False
    account.updated_at = datetime.utcnow()
    db.session.commit()
    _invalidate_account_cache(user_id)
    logger.info("Soft-deleted account id=%s user=%s", account_id, user_id)
    return True


def get_account_overview(user_id: int) -> dict:
    """Compute aggregated view across all accounts: total balance,
    per-account breakdown, recent activity per account."""
    cached = cache_get(account_overview_key(user_id))
    if cached:
        return cached

    accounts = (
        db.session.query(Account)
        .filter_by(user_id=user_id, is_active=True)
        .order_by(Account.created_at.asc())
        .all()
    )

    total_balance = sum(float(a.balance or 0) for a in accounts)

    breakdown = []
    for a in accounts:
        # 最近のアクティビティ（直近5件）
        recent = (
            db.session.query(Expense)
            .filter_by(user_id=user_id, account_id=a.id)
            .order_by(Expense.spent_at.desc(), Expense.id.desc())
            .limit(5)
            .all()
        )
        breakdown.append({
            **account_to_dict(a),
            "recent_activity": [
                {
                    "id": e.id,
                    "description": e.notes or "",
                    "amount": float(e.amount),
                    "date": e.spent_at.isoformat(),
                    "type": e.expense_type,
                }
                for e in recent
            ],
        })

    overview = {
        "total_balance": round(total_balance, 2),
        "account_count": len(accounts),
        "accounts": breakdown,
    }
    cache_set(account_overview_key(user_id), overview, ttl_seconds=300)
    return overview


def recalculate_balance(account_id: int) -> float | None:
    """Recompute account balance from linked expenses."""
    account = db.session.get(Account, account_id)
    if not account:
        return None

    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter_by(user_id=account.user_id, account_id=account_id, expense_type="INCOME")
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == account.user_id,
            Expense.account_id == account_id,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )

    # 初期残高 + 収入 - 支出 でバランスを再計算
    # ここでは初期残高を保持せず、直接 income - expenses でネットフローを計算
    new_balance = float(income or 0) - float(expenses or 0)
    account.balance = Decimal(str(new_balance)).quantize(Decimal("0.01"))
    account.updated_at = datetime.utcnow()
    db.session.commit()
    _invalidate_account_cache(account.user_id)
    logger.info("Recalculated balance account=%s new_balance=%s", account_id, new_balance)
    return round(new_balance, 2)


def account_to_dict(a: Account) -> dict:
    """Serialize an Account model to a dictionary."""
    return {
        "id": a.id,
        "user_id": a.user_id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "balance": float(a.balance or 0),
        "icon": a.icon,
        "color": a.color,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _invalidate_account_cache(user_id: int):
    """Clear all account-related caches for this user."""
    cache_delete_patterns([
        accounts_key(user_id),
        account_overview_key(user_id),
        f"user:{user_id}:dashboard_summary:*",
    ])
