"""Bank-sync API endpoints.

Provides CRUD for bank connections and trigger endpoints for import /
refresh operations.  The actual sync logic lives in
:mod:`app.services.bank_sync`.
"""

from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..connectors.registry import registry
from ..extensions import db
from ..models import BankConnection, SyncLog
from ..services import bank_sync as sync_service

bp = Blueprint("bank_sync", __name__)
logger = logging.getLogger("finmind.routes.bank_sync")


@bp.get("/providers")
@jwt_required()
def list_providers():
    """Return the list of registered connector provider names."""
    return jsonify(providers=registry.available())


@bp.post("/connect")
@jwt_required()
def connect():
    """Authenticate with a bank provider and create a connection."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    provider = (data.get("provider") or "").strip().lower()
    credentials = data.get("credentials") or {}
    config = data.get("config") or {}

    if not provider:
        return jsonify(error="provider required"), 400
    if provider not in registry:
        return jsonify(error=f"unknown provider: {provider}"), 400

    cls = registry.get(provider)
    connector = cls(config)
    connection = sync_service.connect_account(
        user_id=uid,
        provider=provider,
        connector=connector,
        credentials=credentials,
    )
    if connection is None:
        return jsonify(error="authentication failed"), 401
    return (
        jsonify(_connection_to_dict(connection)),
        201,
    )


@bp.get("/connections")
@jwt_required()
def list_connections():
    """List all bank connections for the current user."""
    uid = int(get_jwt_identity())
    items = (
        db.session.query(BankConnection)
        .filter_by(user_id=uid)
        .order_by(BankConnection.created_at.desc())
        .all()
    )
    return jsonify([_connection_to_dict(c) for c in items])


@bp.post("/connections/<int:conn_id>/import")
@jwt_required()
def trigger_import(conn_id: int):
    """Full import of transactions for a date range."""
    uid = int(get_jwt_identity())
    connection = db.session.get(BankConnection, conn_id)
    if not connection or connection.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    try:
        start = date.fromisoformat(data.get("start_date", ""))
        end = date.fromisoformat(data.get("end_date", ""))
    except (ValueError, TypeError):
        return jsonify(error="start_date and end_date required (YYYY-MM-DD)"), 400

    cls = registry.get(connection.provider)
    connector = cls(data.get("config") or {})
    connector.authenticate(data.get("credentials") or {})

    result = sync_service.import_transactions(connection, connector, start, end)
    return jsonify(result), 200


@bp.post("/connections/<int:conn_id>/refresh")
@jwt_required()
def trigger_refresh(conn_id: int):
    """Incremental refresh using the stored cursor."""
    uid = int(get_jwt_identity())
    connection = db.session.get(BankConnection, conn_id)
    if not connection or connection.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    cls = registry.get(connection.provider)
    connector = cls(data.get("config") or {})
    connector.authenticate(data.get("credentials") or {})

    result = sync_service.refresh_transactions(connection, connector)
    return jsonify(result), 200


@bp.get("/connections/<int:conn_id>/logs")
@jwt_required()
def sync_logs(conn_id: int):
    """Return sync history for a connection."""
    uid = int(get_jwt_identity())
    connection = db.session.get(BankConnection, conn_id)
    if not connection or connection.user_id != uid:
        return jsonify(error="not found"), 404

    logs = (
        db.session.query(SyncLog)
        .filter_by(connection_id=conn_id)
        .order_by(SyncLog.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify([_log_to_dict(lg) for lg in logs])


@bp.delete("/connections/<int:conn_id>")
@jwt_required()
def disconnect(conn_id: int):
    """Disconnect (soft-delete) a bank connection."""
    uid = int(get_jwt_identity())
    connection = db.session.get(BankConnection, conn_id)
    if not connection or connection.user_id != uid:
        return jsonify(error="not found"), 404

    sync_service.disconnect_account(connection)
    return jsonify(message="disconnected"), 200


# ------------------------------------------------------------------
# Serialisers
# ------------------------------------------------------------------


def _connection_to_dict(c: BankConnection) -> dict:
    return {
        "id": c.id,
        "provider": c.provider,
        "external_account_id": c.external_account_id,
        "account_name": c.account_name,
        "account_type": c.account_type,
        "currency": c.currency,
        "status": c.status,
        "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _log_to_dict(lg: SyncLog) -> dict:
    return {
        "id": lg.id,
        "sync_type": lg.sync_type,
        "status": lg.status,
        "records_imported": lg.records_imported,
        "duplicates_skipped": lg.duplicates_skipped,
        "error_message": lg.error_message,
        "started_at": lg.started_at.isoformat() if lg.started_at else None,
        "completed_at": lg.completed_at.isoformat() if lg.completed_at else None,
    }
