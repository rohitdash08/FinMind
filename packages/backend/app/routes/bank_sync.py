import logging
from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import BankAccount, Expense, User
from ..services import bank_sync
from ..services.cache import cache_delete_patterns, monthly_summary_key

bp = Blueprint("bank_sync", __name__)
logger = logging.getLogger("finmind.bank_sync")


@bp.get("/connectors")
@jwt_required()
def list_connectors():
    return jsonify(bank_sync.list_connectors())


@bp.get("/accounts")
@jwt_required()
def list_accounts():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(BankAccount)
        .filter_by(user_id=uid)
        .order_by(BankAccount.created_at.desc())
        .all()
    )
    return jsonify([_account_to_dict(a) for a in items])


@bp.post("/accounts")
@jwt_required()
def link_account():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    provider = (data.get("provider") or "").strip().lower()
    credentials = data.get("credentials") or {}
    if not provider:
        return jsonify(error="provider required"), 400
    try:
        connector = bank_sync.get_connector(provider)
    except KeyError:
        return jsonify(error=f"unknown provider: {provider}"), 404
    try:
        accounts = connector.connect(credentials)
    except bank_sync.ConnectorError as exc:
        return jsonify(error=str(exc)), 400

    requested_id = data.get("external_id")
    if requested_id:
        accounts = [a for a in accounts if a.external_id == requested_id]
        if not accounts:
            return jsonify(error="account not available from connector"), 404

    created: list[BankAccount] = []
    for info in accounts:
        existing = (
            db.session.query(BankAccount)
            .filter_by(user_id=uid, provider=provider, external_id=info.external_id)
            .first()
        )
        if existing:
            created.append(existing)
            continue
        account = BankAccount(
            user_id=uid,
            provider=provider,
            external_id=info.external_id,
            name=info.name,
            account_type=info.account_type,
            currency=info.currency,
        )
        db.session.add(account)
        created.append(account)
    db.session.commit()
    logger.info(
        "Linked bank accounts user=%s provider=%s count=%s",
        uid,
        provider,
        len(created),
    )
    return jsonify([_account_to_dict(a) for a in created]), 201


@bp.delete("/accounts/<int:account_id>")
@jwt_required()
def unlink_account(account_id: int):
    uid = int(get_jwt_identity())
    account = db.session.get(BankAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(account)
    db.session.commit()
    return jsonify(message="deleted")


@bp.post("/accounts/<int:account_id>/import")
@jwt_required()
def import_account(account_id: int):
    return _sync_account(account_id, mode="import")


@bp.post("/accounts/<int:account_id>/refresh")
@jwt_required()
def refresh_account(account_id: int):
    return _sync_account(account_id, mode="refresh")


def _sync_account(account_id: int, *, mode: str):
    uid = int(get_jwt_identity())
    account = db.session.get(BankAccount, account_id)
    if not account or account.user_id != uid:
        return jsonify(error="not found"), 404
    try:
        connector = bank_sync.get_connector(account.provider)
    except KeyError:
        return jsonify(error=f"unknown provider: {account.provider}"), 400

    since: date | None = None
    if mode == "refresh" and account.last_synced_at:
        since = account.last_synced_at.date()

    try:
        transactions = connector.fetch_transactions(
            account.external_id, since=since
        )
    except bank_sync.ConnectorError as exc:
        return jsonify(error=str(exc)), 400

    user = db.session.get(User, uid)
    fallback_currency = (
        account.currency or (user.preferred_currency if user else "USD")
    )

    inserted = 0
    duplicates = 0
    touched_months: set[str] = set()
    for tx in transactions:
        if _is_duplicate_tx(uid, tx):
            duplicates += 1
            continue
        expense = Expense(
            user_id=uid,
            amount=Decimal(str(tx.amount)).quantize(Decimal("0.01")),
            currency=tx.currency or fallback_currency,
            expense_type=(tx.expense_type or "EXPENSE").upper(),
            notes=tx.description[:500],
            spent_at=tx.date,
        )
        db.session.add(expense)
        inserted += 1
        touched_months.add(tx.date.strftime("%Y-%m"))

    account.last_synced_at = datetime.utcnow()
    db.session.commit()
    for ym in touched_months:
        cache_delete_patterns(
            [
                monthly_summary_key(uid, ym),
                f"insights:{uid}:*",
                f"user:{uid}:dashboard_summary:*",
            ]
        )
    logger.info(
        "Bank sync %s user=%s account=%s inserted=%s duplicates=%s",
        mode,
        uid,
        account_id,
        inserted,
        duplicates,
    )
    return jsonify(
        mode=mode,
        inserted=inserted,
        duplicates=duplicates,
        last_synced_at=account.last_synced_at.isoformat(),
    )


def _is_duplicate_tx(uid: int, tx) -> bool:
    amount = Decimal(str(tx.amount)).quantize(Decimal("0.01"))
    return (
        db.session.query(Expense)
        .filter_by(
            user_id=uid,
            spent_at=tx.date,
            amount=amount,
            notes=tx.description[:500],
        )
        .first()
        is not None
    )


def _account_to_dict(a: BankAccount) -> dict:
    return {
        "id": a.id,
        "provider": a.provider,
        "external_id": a.external_id,
        "name": a.name,
        "account_type": a.account_type,
        "currency": a.currency,
        "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
