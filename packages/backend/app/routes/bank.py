"""Bank sync routes — connect, list accounts, sync, refresh."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import BankConnection, BankTransaction
from ..services.bank_sync import (
    connect_bank,
    list_bank_accounts,
    sync_transactions,
    refresh_connection,
)
from ..services.bank_connector import ConnectorRegistry
import logging

bp = Blueprint("bank", __name__)
logger = logging.getLogger("finmind.bank")


@bp.get("/providers")
@jwt_required()
def list_providers():
    """List available bank connector providers."""
    return jsonify({"providers": ConnectorRegistry.list_providers()})


@bp.post("/connect")
@jwt_required()
def create_connection():
    """Connect to a bank provider."""
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)

    provider = (data.get("provider") or "").strip()
    credentials = data.get("credentials", {})

    if not provider:
        return jsonify({"error": "provider is required"}), 400

    try:
        conn = connect_bank(uid, provider, credentials)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "id": conn.id,
        "provider": conn.provider,
        "status": conn.status,
        "created_at": conn.created_at.isoformat(),
    }), 201


@bp.get("/connections")
@jwt_required()
def list_connections():
    """List user's bank connections."""
    uid = int(get_jwt_identity())
    connections = BankConnection.query.filter_by(user_id=uid).all()
    return jsonify([
        {
            "id": c.id,
            "provider": c.provider,
            "account_name": c.account_name,
            "status": c.status,
            "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
            "created_at": c.created_at.isoformat(),
        }
        for c in connections
    ])


@bp.get("/connections/<int:conn_id>/accounts")
@jwt_required()
def get_accounts(conn_id: int):
    """List bank accounts available through a connection."""
    uid = int(get_jwt_identity())
    try:
        accounts = list_bank_accounts(conn_id, uid)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify(accounts)


@bp.post("/connections/<int:conn_id>/sync")
@jwt_required()
def sync(conn_id: int):
    """Sync transactions from a bank connection."""
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)

    account_id = (data.get("account_id") or "").strip()
    days = data.get("days", 30)

    if not account_id:
        return jsonify({"error": "account_id is required"}), 400

    try:
        result = sync_transactions(conn_id, uid, account_id, days)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(result)


@bp.post("/connections/<int:conn_id>/refresh")
@jwt_required()
def refresh(conn_id: int):
    """Refresh a bank connection."""
    uid = int(get_jwt_identity())
    try:
        result = refresh_connection(conn_id, uid)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(result)


@bp.get("/connections/<int:conn_id>/transactions")
@jwt_required()
def get_transactions(conn_id: int):
    """List imported transactions for a connection."""
    uid = int(get_jwt_identity())
    conn = BankConnection.query.filter_by(id=conn_id, user_id=uid).first()
    if not conn:
        return jsonify({"error": "connection not found"}), 404

    transactions = BankTransaction.query.filter_by(
        connection_id=conn_id, user_id=uid
    ).order_by(BankTransaction.transaction_date.desc()).limit(200).all()

    return jsonify([
        {
            "id": t.id,
            "external_id": t.external_id,
            "amount": float(t.amount),
            "currency": t.currency,
            "description": t.description,
            "category": t.category,
            "date": str(t.transaction_date),
        }
        for t in transactions
    ])


@bp.delete("/connections/<int:conn_id>")
@jwt_required()
def delete_connection(conn_id: int):
    """Delete a bank connection and its transactions."""
    uid = int(get_jwt_identity())
    conn = BankConnection.query.filter_by(id=conn_id, user_id=uid).first()
    if not conn:
        return jsonify({"error": "not found"}), 404

    BankTransaction.query.filter_by(connection_id=conn_id).delete()
    db.session.delete(conn)
    db.session.commit()
    return jsonify({"message": "deleted"})
