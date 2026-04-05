"""
Bank Sync API Routes

Provides endpoints for:
- Listing available bank connectors
- Connecting/disconnecting bank accounts
- Importing and refreshing transactions
"""

from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import bank_sync as bank_sync_service

bp = Blueprint("bank_sync", __name__)


@bp.get("/connectors")
@jwt_required()
def list_connectors():
    """List all available bank connectors."""
    connectors = bank_sync_service.BankSyncService.list_available_connectors()
    return jsonify(connectors)


@bp.post("/connect")
@jwt_required()
def connect_bank():
    """Connect to a bank connector."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    connector_type = data.get("connector_type")
    if not connector_type:
        return jsonify(error="connector_type required"), 400
    
    credentials = data.get("credentials", {})
    
    result = bank_sync_service.BankSyncService.connect(
        user_id=uid,
        connector_type=connector_type,
        credentials=credentials,
    )
    
    if not result.get("success"):
        return jsonify(error=result.get("error", "Connection failed")), 400
    
    return jsonify(result), 200


@bp.post("/disconnect")
@jwt_required()
def disconnect_bank():
    """Disconnect from a bank connector."""
    data = request.get_json() or {}
    
    connector_type = data.get("connector_type")
    if not connector_type:
        return jsonify(error="connector_type required"), 400
    
    result = bank_sync_service.BankSyncService.disconnect(connector_type)
    
    if not result.get("success"):
        return jsonify(error=result.get("error", "Disconnect failed")), 400
    
    return jsonify(result), 200


@bp.get("/status")
@jwt_required()
def get_status():
    """Get connection status for a connector."""
    connector_type = request.args.get("connector_type")
    if not connector_type:
        return jsonify(error="connector_type required"), 400
    
    status = bank_sync_service.BankSyncService.get_connection_status(connector_type)
    return jsonify(status)


@bp.get("/accounts")
@jwt_required()
def get_accounts():
    """Get accounts from a connected connector."""
    connector_type = request.args.get("connector_type")
    if not connector_type:
        return jsonify(error="connector_type required"), 400
    
    accounts = bank_sync_service.BankSyncService.get_accounts(connector_type)
    return jsonify(accounts)


@bp.post("/import")
@jwt_required()
def import_transactions():
    """Import transactions from a connected bank account."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    connector_type = data.get("connector_type")
    account_id = data.get("account_id")
    
    if not connector_type:
        return jsonify(error="connector_type required"), 400
    if not account_id:
        return jsonify(error="account_id required"), 400
    
    # Parse optional date filters
    from_date = None
    to_date = None
    
    if data.get("from_date"):
        try:
            from_date = date.fromisoformat(data["from_date"])
        except ValueError:
            return jsonify(error="invalid from_date format"), 400
    
    if data.get("to_date"):
        try:
            to_date = date.fromisoformat(data["to_date"])
        except ValueError:
            return jsonify(error="invalid to_date format"), 400
    
    result = bank_sync_service.BankSyncService.import_transactions(
        user_id=uid,
        connector_type=connector_type,
        account_id=account_id,
        from_date=from_date,
        to_date=to_date,
    )
    
    if not result.get("success"):
        return jsonify(error=result.get("error", "Import failed")), 400
    
    return jsonify(result), 200


@bp.post("/refresh")
@jwt_required()
def refresh_transactions():
    """Refresh new transactions from a connected account."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    connector_type = data.get("connector_type")
    account_id = data.get("account_id")
    since_raw = data.get("since")
    
    if not connector_type:
        return jsonify(error="connector_type required"), 400
    if not account_id:
        return jsonify(error="account_id required"), 400
    if not since_raw:
        return jsonify(error="since required"), 400
    
    try:
        since = datetime.fromisoformat(since_raw)
    except ValueError:
        return jsonify(error="invalid since format"), 400
    
    result = bank_sync_service.BankSyncService.refresh_transactions(
        user_id=uid,
        connector_type=connector_type,
        account_id=account_id,
        since=since,
    )
    
    if not result.get("success"):
        return jsonify(error=result.get("error", "Refresh failed")), 400
    
    return jsonify(result), 200


@bp.post("/commit")
@jwt_required()
def commit_transactions():
    """Commit imported transactions to the database."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    transactions = data.get("transactions", [])
    if not transactions:
        return jsonify(error="transactions required"), 400
    
    result = bank_sync_service.BankSyncService.commit_transactions(
        user_id=uid,
        transactions=transactions,
    )
    
    if not result.get("success"):
        return jsonify(error=result.get("error", "Commit failed")), 400
    
    return jsonify(result), 201


@bp.get("/import/preview")
@jwt_required()
def import_preview():
    """
    Preview imported transactions (alias for /import for compatibility).
    """
    return import_transactions()


@bp.post("/import/commit")
@jwt_required()
def import_commit():
    """
    Commit imported transactions (alias for /commit for compatibility).
    """
    return commit_transactions()