"""Bank sync connector routes.

Endpoints
---------
GET  /bank-sync/providers
    List all registered connector providers.

POST /bank-sync/providers/<provider_id>/accounts
    Fetch accounts for a provider using supplied credentials.

POST /bank-sync/connections
    Create (connect) a new bank connection for the authenticated user.

GET  /bank-sync/connections
    List the authenticated user's bank connections.

DELETE /bank-sync/connections/<connection_id>
    Remove a bank connection.

POST /bank-sync/connections/<connection_id>/import
    Full import of transactions for a date range.

POST /bank-sync/connections/<connection_id>/refresh
    Incremental sync using the stored cursor.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import BankConnection, Expense, User
from ..services import bank_connectors
from ..services.expense_import import normalize_import_rows

bp = Blueprint("bank_sync", __name__)
logger = logging.getLogger("finmind.bank_sync")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _connection_to_dict(conn: BankConnection) -> dict:
    return {
        "id": conn.id,
        "provider_id": conn.provider_id,
        "account_id": conn.account_id,
        "account_name": conn.account_name,
        "account_type": conn.account_type,
        "institution_name": conn.institution_name,
        "masked_account_number": conn.masked_account_number,
        "currency": conn.currency,
        "sync_cursor": conn.sync_cursor,
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
        "active": conn.active,
        "created_at": conn.created_at.isoformat(),
    }


def _tx_to_expense_row(tx, currency: str) -> dict:
    return {
        "date": tx.transaction_date.isoformat(),
        "amount": tx.amount,
        "description": tx.description,
        "category_id": None,
        "expense_type": "INCOME" if tx.transaction_type == "CREDIT" else "EXPENSE",
        "currency": tx.currency or currency,
    }


def _is_duplicate(uid: int, row: dict) -> bool:
    from decimal import Decimal

    try:
        amount = Decimal(str(row["amount"])).quantize(Decimal("0.01"))
    except Exception:
        return False
    return (
        db.session.query(Expense)
        .filter_by(
            user_id=uid,
            spent_at=date.fromisoformat(row["date"]),
            amount=amount,
            notes=row["description"],
        )
        .first()
        is not None
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.get("/providers")
@jwt_required()
def list_providers():
    """Return all available connector providers."""
    providers = [
        {"provider_id": c.provider_id, "display_name": c.display_name}
        for c in bank_connectors.list_connectors()
    ]
    return jsonify(providers)


@bp.post("/providers/<provider_id>/accounts")
@jwt_required()
def fetch_provider_accounts(provider_id: str):
    """Fetch accounts for *provider_id* using the supplied credentials."""
    connector = bank_connectors.get_connector(provider_id)
    if not connector:
        return jsonify(error=f"unknown provider: {provider_id}"), 404
    credentials = request.get_json() or {}
    try:
        accounts = connector.fetch_accounts(credentials)
    except Exception as exc:
        logger.exception("fetch_accounts failed provider=%s", provider_id)
        return jsonify(error=f"failed to fetch accounts: {exc}"), 502
    return jsonify(
        [
            {
                "account_id": a.account_id,
                "account_name": a.account_name,
                "account_type": a.account_type,
                "balance": a.balance,
                "currency": a.currency,
                "institution_name": a.institution_name,
                "masked_account_number": a.masked_account_number,
            }
            for a in accounts
        ]
    )


@bp.post("/connections")
@jwt_required()
def create_connection():
    """Connect a bank account for the authenticated user."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    provider_id = (data.get("provider_id") or "").strip()
    account_id = (data.get("account_id") or "").strip()
    if not provider_id:
        return jsonify(error="provider_id required"), 400
    if not account_id:
        return jsonify(error="account_id required"), 400
    connector = bank_connectors.get_connector(provider_id)
    if not connector:
        return jsonify(error=f"unknown provider: {provider_id}"), 404
    credentials = data.get("credentials") or {}
    # Verify the account exists
    try:
        accounts = connector.fetch_accounts(credentials)
    except Exception as exc:
        logger.exception("create_connection fetch_accounts failed provider=%s", provider_id)
        return jsonify(error=f"failed to verify credentials: {exc}"), 502
    account = next((a for a in accounts if a.account_id == account_id), None)
    if not account:
        return jsonify(error="account_id not found for given credentials"), 404
    # Check for duplicate connection
    existing = (
        db.session.query(BankConnection)
        .filter_by(user_id=uid, provider_id=provider_id, account_id=account_id, active=True)
        .first()
    )
    if existing:
        return jsonify(error="connection already exists"), 409
    conn = BankConnection(
        user_id=uid,
        provider_id=provider_id,
        account_id=account.account_id,
        account_name=account.account_name,
        account_type=account.account_type,
        institution_name=account.institution_name,
        masked_account_number=account.masked_account_number,
        currency=account.currency,
        credentials_json=json.dumps(credentials),
    )
    db.session.add(conn)
    db.session.commit()
    logger.info("BankConnection created id=%s user=%s provider=%s", conn.id, uid, provider_id)
    return jsonify(_connection_to_dict(conn)), 201


@bp.get("/connections")
@jwt_required()
def list_connections():
    """List bank connections for the authenticated user."""
    uid = int(get_jwt_identity())
    conns = (
        db.session.query(BankConnection)
        .filter_by(user_id=uid, active=True)
        .order_by(BankConnection.created_at.desc())
        .all()
    )
    return jsonify([_connection_to_dict(c) for c in conns])


@bp.delete("/connections/<int:connection_id>")
@jwt_required()
def delete_connection(connection_id: int):
    """Soft-delete a bank connection."""
    uid = int(get_jwt_identity())
    conn = db.session.get(BankConnection, connection_id)
    if not conn or conn.user_id != uid:
        return jsonify(error="not found"), 404
    conn.active = False
    db.session.commit()
    return jsonify(message="connection removed")


@bp.post("/connections/<int:connection_id>/import")
@jwt_required()
def import_transactions(connection_id: int):
    """Full import of transactions for a date range.

    Request body::

        {
            "from_date": "2024-01-01",
            "to_date": "2024-03-31",
            "commit": true   // if false (default) returns preview only
        }
    """
    uid = int(get_jwt_identity())
    conn = db.session.get(BankConnection, connection_id)
    if not conn or conn.user_id != uid or not conn.active:
        return jsonify(error="not found"), 404
    connector = bank_connectors.get_connector(conn.provider_id)
    if not connector:
        return jsonify(error=f"provider {conn.provider_id} no longer available"), 404
    data = request.get_json() or {}
    from_raw = data.get("from_date")
    to_raw = data.get("to_date")
    if not from_raw or not to_raw:
        return jsonify(error="from_date and to_date required"), 400
    try:
        from_date = date.fromisoformat(from_raw)
        to_date = date.fromisoformat(to_raw)
    except ValueError:
        return jsonify(error="invalid date format, use YYYY-MM-DD"), 400
    if from_date > to_date:
        return jsonify(error="from_date must be on or before to_date"), 400
    commit = bool(data.get("commit", False))
    try:
        credentials = json.loads(conn.credentials_json or "{}")
        result = connector.import_transactions(
            credentials, conn.account_id, from_date, to_date
        )
    except Exception as exc:
        logger.exception("import_transactions failed connection=%s", connection_id)
        return jsonify(error=f"connector error: {exc}"), 502
    rows = [_tx_to_expense_row(tx, conn.currency) for tx in result.transactions]
    normalized = normalize_import_rows(rows)
    duplicates_count = sum(1 for r in normalized if _is_duplicate(uid, r))
    if not commit:
        return jsonify(
            total=len(normalized),
            duplicates=duplicates_count,
            transactions=normalized,
            cursor=result.cursor,
        )
    # Commit
    user = db.session.get(User, uid)
    inserted = 0
    skipped = 0
    from decimal import Decimal
    from ..models import Expense as ExpenseModel
    for r in normalized:
        if _is_duplicate(uid, r):
            skipped += 1
            continue
        exp = ExpenseModel(
            user_id=uid,
            amount=Decimal(str(r["amount"])),
            currency=r.get("currency") or (user.preferred_currency if user else "INR"),
            expense_type=str(r.get("expense_type") or "EXPENSE").upper(),
            category_id=r.get("category_id"),
            notes=r["description"],
            spent_at=date.fromisoformat(r["date"]),
        )
        db.session.add(exp)
        inserted += 1
    # Update connection sync cursor
    if result.cursor:
        conn.sync_cursor = result.cursor
    conn.last_synced_at = datetime.utcnow()
    db.session.commit()
    logger.info(
        "import_transactions committed connection=%s inserted=%s skipped=%s",
        connection_id, inserted, skipped,
    )
    return jsonify(inserted=inserted, duplicates=skipped, cursor=result.cursor), 201


@bp.post("/connections/<int:connection_id>/refresh")
@jwt_required()
def refresh_connection(connection_id: int):
    """Incrementally sync new transactions using the stored cursor.

    Fetches transactions since the last sync cursor and commits them as
    expenses.  Returns ``inserted`` and ``cursor`` in the response.
    """
    uid = int(get_jwt_identity())
    conn = db.session.get(BankConnection, connection_id)
    if not conn or conn.user_id != uid or not conn.active:
        return jsonify(error="not found"), 404
    connector = bank_connectors.get_connector(conn.provider_id)
    if not connector:
        return jsonify(error=f"provider {conn.provider_id} no longer available"), 404
    try:
        credentials = json.loads(conn.credentials_json or "{}")
        result = connector.refresh(credentials, conn.account_id, cursor=conn.sync_cursor)
    except Exception as exc:
        logger.exception("refresh failed connection=%s", connection_id)
        return jsonify(error=f"connector error: {exc}"), 502
    rows = [_tx_to_expense_row(tx, conn.currency) for tx in result.transactions]
    normalized = normalize_import_rows(rows)
    user = db.session.get(User, uid)
    inserted = 0
    skipped = 0
    from decimal import Decimal
    from ..models import Expense as ExpenseModel
    for r in normalized:
        if _is_duplicate(uid, r):
            skipped += 1
            continue
        exp = ExpenseModel(
            user_id=uid,
            amount=Decimal(str(r["amount"])),
            currency=r.get("currency") or (user.preferred_currency if user else "INR"),
            expense_type=str(r.get("expense_type") or "EXPENSE").upper(),
            category_id=r.get("category_id"),
            notes=r["description"],
            spent_at=date.fromisoformat(r["date"]),
        )
        db.session.add(exp)
        inserted += 1
    if result.cursor:
        conn.sync_cursor = result.cursor
    conn.last_synced_at = datetime.utcnow()
    db.session.commit()
    logger.info(
        "refresh committed connection=%s inserted=%s skipped=%s cursor=%s",
        connection_id, inserted, skipped, result.cursor,
    )
    return jsonify(inserted=inserted, duplicates=skipped, cursor=result.cursor), 200
