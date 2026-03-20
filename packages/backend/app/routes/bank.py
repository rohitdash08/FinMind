"""
Bank Sync routes — register as blueprint in FinMind's __init__.py:

    from app.routes.bank import bank_bp
    app.register_blueprint(bank_bp, url_prefix="/api/bank")
"""

import os
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models import BankAccount as BankAccountModel, BankTransaction as BankTransactionModel
from app.services.bank_connector import get_connector, ConsentStatus

bank_bp = Blueprint("bank", __name__)


def _get_connector(provider: str):
    """Instantiate the right connector from env config."""
    if provider == "setu":
        return get_connector(
            "setu",
            client_id=os.environ["SETU_CLIENT_ID"],
            client_secret=os.environ["SETU_CLIENT_SECRET"],
            base_url=os.environ.get("SETU_BASE_URL", "https://fiu-uat.setu.co"),
        )
    return get_connector(provider)   # mock or any registered connector


# ─── Consent flow ────────────────────────────────────────────────────────────

@bank_bp.post("/connect")
@jwt_required()
def initiate_connect():
    """
    Start AA consent flow.

    Body: { "provider": "setu" | "mock" }
    Returns: { "redirect_url": "...", "handle_id": "..." }
    """
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "mock")
    redirect_uri = request.host_url.rstrip("/") + "/bank/callback"

    connector = _get_connector(provider)
    handle = connector.initiate_consent(str(user_id), redirect_uri)

    return jsonify({
        "handle_id": handle.handle_id,
        "redirect_url": handle.redirect_url,
        "provider": provider,
    }), 202


@bank_bp.get("/callback")
@jwt_required()
def consent_callback():
    """
    AA redirects the user here after approval/rejection.
    Query params: handle=<handle_id>&provider=<provider>
    """
    user_id = get_jwt_identity()
    handle_id = request.args.get("handle")
    provider = request.args.get("provider", "mock")

    if not handle_id:
        return jsonify({"error": "Missing handle"}), 400

    # Reconstruct a minimal ConsentHandle to confirm
    from app.services.bank_connector import ConsentHandle
    handle = ConsentHandle(handle_id=handle_id, redirect_url="")
    connector = _get_connector(provider)
    handle = connector.confirm_consent(handle, dict(request.args))

    if handle.status != ConsentStatus.ACTIVE:
        return jsonify({"error": "Consent not approved", "status": handle.status}), 400

    # Fetch and persist linked accounts
    accounts = connector.fetch_accounts(handle)
    saved = []
    for acc in accounts:
        existing = BankAccountModel.query.filter_by(
            user_id=user_id, provider=provider, account_id=acc.account_id
        ).first()
        if not existing:
            existing = BankAccountModel(
                user_id=user_id,
                provider=provider,
                account_id=acc.account_id,
            )
            db.session.add(existing)

        existing.masked_account_number = acc.masked_account_number
        existing.bank_name = acc.bank_name
        existing.ifsc = acc.ifsc
        existing.account_type = acc.account_type
        existing.currency = acc.currency
        existing.holder_name = acc.holder_name
        existing.consent_handle_id = handle.handle_id
        existing.consent_artefact_id = handle.artefact_id
        existing.consent_status = handle.status.value
        saved.append(existing)

    db.session.commit()
    return jsonify({"accounts": [a.to_dict() for a in saved]}), 200


# ─── Account management ──────────────────────────────────────────────────────

@bank_bp.get("/accounts")
@jwt_required()
def list_accounts():
    """List all linked bank accounts for the current user."""
    user_id = get_jwt_identity()
    accounts = BankAccountModel.query.filter_by(user_id=user_id).all()
    return jsonify({"accounts": [a.to_dict() for a in accounts]}), 200


@bank_bp.delete("/accounts/<account_uuid>")
@jwt_required()
def disconnect_account(account_uuid: str):
    """Revoke consent and remove the linked account."""
    user_id = get_jwt_identity()
    acc = BankAccountModel.query.filter_by(id=account_uuid, user_id=user_id).first_or_404()
    db.session.delete(acc)
    db.session.commit()
    return jsonify({"message": "Account disconnected"}), 200


# ─── Import & Refresh ────────────────────────────────────────────────────────

@bank_bp.post("/accounts/<account_uuid>/import")
@jwt_required()
def import_transactions(account_uuid: str):
    """
    Full historical import for a linked account.

    Body (optional): { "from_date": "YYYY-MM-DD", "to_date": "YYYY-MM-DD" }
    Defaults to the last 12 months.
    """
    user_id = get_jwt_identity()
    acc = BankAccountModel.query.filter_by(id=account_uuid, user_id=user_id).first_or_404()

    data = request.get_json(silent=True) or {}
    to_date = date.fromisoformat(data["to_date"]) if "to_date" in data else date.today()
    from_date = date.fromisoformat(data["from_date"]) if "from_date" in data else to_date - timedelta(days=365)

    connector = _get_connector(acc.provider)
    handle = _rebuild_handle(acc)
    transactions = connector.import_transactions(handle, acc.account_id, from_date, to_date)

    inserted = _upsert_transactions(acc.id, transactions)
    acc.last_synced_at = date.today()
    db.session.commit()

    return jsonify({"imported": inserted, "from": from_date.isoformat(), "to": to_date.isoformat()}), 200


@bank_bp.post("/accounts/<account_uuid>/refresh")
@jwt_required()
def refresh_transactions(account_uuid: str):
    """Incremental sync — fetch transactions since last_synced_at."""
    user_id = get_jwt_identity()
    acc = BankAccountModel.query.filter_by(id=account_uuid, user_id=user_id).first_or_404()

    last_synced = acc.last_synced_at or (date.today() - timedelta(days=30))
    connector = _get_connector(acc.provider)
    handle = _rebuild_handle(acc)
    transactions = connector.refresh(handle, acc.account_id, last_synced)

    inserted = _upsert_transactions(acc.id, transactions)
    acc.last_synced_at = date.today()
    db.session.commit()

    return jsonify({"refreshed": inserted, "since": last_synced.isoformat()}), 200


@bank_bp.get("/accounts/<account_uuid>/transactions")
@jwt_required()
def get_transactions(account_uuid: str):
    """List stored bank transactions for an account with optional date filters."""
    user_id = get_jwt_identity()
    acc = BankAccountModel.query.filter_by(id=account_uuid, user_id=user_id).first_or_404()

    from_date = request.args.get("from")
    to_date = request.args.get("to")

    q = BankTransactionModel.query.filter_by(bank_account_id=acc.id)
    if from_date:
        q = q.filter(BankTransactionModel.date >= date.fromisoformat(from_date))
    if to_date:
        q = q.filter(BankTransactionModel.date <= date.fromisoformat(to_date))

    txns = q.order_by(BankTransactionModel.date.desc()).all()
    return jsonify({"transactions": [t.to_dict() for t in txns]}), 200


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _rebuild_handle(acc: BankAccountModel):
    from app.services.bank_connector import ConsentHandle, ConsentStatus
    return ConsentHandle(
        handle_id=acc.consent_handle_id or "",
        redirect_url="",
        status=ConsentStatus[acc.consent_status] if acc.consent_status in ConsentStatus.__members__ else ConsentStatus.PENDING,
        artefact_id=acc.consent_artefact_id,
    )


def _upsert_transactions(bank_account_id: str, transactions) -> int:
    """Insert new transactions, skip duplicates. Returns count inserted."""
    inserted = 0
    for txn in transactions:
        exists = BankTransactionModel.query.filter_by(
            bank_account_id=bank_account_id,
            transaction_id=txn.transaction_id,
        ).first()
        if not exists:
            row = BankTransactionModel(
                bank_account_id=bank_account_id,
                transaction_id=txn.transaction_id,
                amount=txn.amount,
                currency=txn.currency,
                transaction_type=txn.transaction_type.value,
                description=txn.description,
                date=txn.date,
                balance=txn.balance,
                category_hint=txn.category_hint,
                raw=txn.raw,
            )
            db.session.add(row)
            inserted += 1
    return inserted
