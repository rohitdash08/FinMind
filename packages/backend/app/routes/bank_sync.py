"""Bank Sync API Routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..services.bank_sync import BankSyncService
from ..services.bank_connector import ConnectorRegistry

bp = Blueprint("bank_sync", __name__)
service = BankSyncService()


@bp.get("/connectors")
@jwt_required()
def list_connectors():
    """List available bank connectors.
    
    Returns:
        JSON list of available connectors
    """
    connectors = service.list_available_connectors()
    return jsonify([
        {"id": cid, "name": name}
        for cid, name in connectors.items()
    ])


@bp.post("/connect")
@jwt_required()
def connect_bank():
    """Connect to a bank.
    
    Request body:
        {
            "connector_id": "mock",
            "credentials": {"api_key": "..."},
            "config": {"account_count": 3}
        }
    
    Returns:
        Connection status and available accounts
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    connector_id = data.get("connector_id")
    credentials = data.get("credentials", {})
    config = data.get("config", {})
    
    if not connector_id:
        return jsonify(error="connector_id required"), 400
    
    # Connect to bank
    connector = service.connect_bank(connector_id, credentials, config)
    if not connector:
        return jsonify(error="Failed to connect to bank"), 400
    
    # Sync accounts
    result = service.sync_accounts(uid, connector)
    
    if not result.success:
        return jsonify(
            error="Failed to sync accounts",
            errors=result.errors
        ), 400
    
    # Get account details
    accounts = connector.fetch_accounts()
    
    return jsonify({
        "connected": True,
        "connector_id": connector_id,
        "accounts_synced": result.accounts_synced,
        "accounts": [
            {
                "id": acc.id,
                "name": acc.name,
                "type": acc.account_type,
                "currency": acc.currency,
                "balance": float(acc.balance),
                "account_number_masked": acc.account_number_masked,
                "institution": acc.institution_name,
            }
            for acc in accounts
        ],
    })


@bp.post("/sync/<account_id>")
@jwt_required()
def sync_transactions(account_id: str):
    """Sync transactions for a specific account.
    
    Request body (optional):
        {
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "import_to_expenses": true
        }
    
    Args:
        account_id: The bank account ID
        
    Returns:
        Sync result with transactions
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    # This is a simplified version - in production you'd store
    # the connector in session/database
    connector_id = data.get("connector_id", "mock")
    credentials = data.get("credentials", {"api_key": "test"})
    config = data.get("config", {})
    
    # Reconnect (in production, use stored tokens)
    connector = service.connect_bank(connector_id, credentials, config)
    if not connector:
        return jsonify(error="Failed to connect to bank"), 400
    
    from datetime import date
    
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    import_to_expenses = data.get("import_to_expenses", True)
    
    if start_date:
        start_date = date.fromisoformat(start_date)
    if end_date:
        end_date = date.fromisoformat(end_date)
    
    result = service.sync_transactions(
        user_id=uid,
        connector=connector,
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        import_to_expenses=import_to_expenses
    )
    
    if not result.success:
        return jsonify(
            error="Failed to sync transactions",
            errors=result.errors
        ), 400
    
    return jsonify({
        "success": True,
        "transactions_synced": result.transactions_synced,
        "transactions": [
            {
                "id": tx.id,
                "date": tx.date.isoformat(),
                "amount": float(tx.amount),
                "description": tx.description,
                "currency": tx.currency,
                "merchant": tx.merchant_name,
                "pending": tx.pending,
            }
            for tx in result.new_transactions[:50]  # Limit response size
        ],
    })


@bp.get("/status")
@jwt_required()
def connection_status():
    """Get bank connection status.
    
    Query params:
        connector_id: The connector ID
        
    Returns:
        Connection status
    """
    connector_id = request.args.get("connector_id", "mock")
    credentials = {"api_key": "test"}  # In production, use stored tokens
    config = {}
    
    connector = service.connect_bank(connector_id, credentials, config)
    if not connector:
        return jsonify(error="Not connected"), 400
    
    status = service.get_connector_status(connector)
    
    return jsonify(status)


@bp.post("/disconnect")
@jwt_required()
def disconnect_bank():
    """Disconnect from a bank.
    
    Request body:
        {
            "connector_id": "mock"
        }
        
    Returns:
        Disconnection status
    """
    data = request.get_json() or {}
    connector_id = data.get("connector_id", "mock")
    credentials = {"api_key": "test"}
    config = {}
    
    connector = service.connect_bank(connector_id, credentials, config)
    if not connector:
        return jsonify(error="Not connected"), 400
    
    success = service.disconnect_bank(connector)
    
    return jsonify({"disconnected": success})
