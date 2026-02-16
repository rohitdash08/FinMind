"""
Bank sync API routes.

Provides REST endpoints for:
  - Connecting/disconnecting bank providers
  - Listing linked accounts
  - Importing transactions
  - Refreshing account data
  - Listing available providers
"""

from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.bank_sync import get_connector, MockBankConnector
from ..services.bank_sync.registry import list_providers, register_connector
from ..services.bank_sync.service import BankSyncService

bp = Blueprint("bank_sync", __name__)

# Register the mock connector on import
register_connector("mock", MockBankConnector)


@bp.route("/providers", methods=["GET"])
@jwt_required()
def get_providers():
    """List available bank sync providers."""
    providers = list_providers()
    return jsonify({"providers": providers}), 200


@bp.route("/connect", methods=["POST"])
@jwt_required()
def connect():
    """
    Connect to a bank provider.

    JSON body:
        provider: str (required) — provider name (e.g., 'mock')
        credentials: dict (optional) — provider-specific credentials
        config: dict (optional) — provider configuration
    """
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    provider = data.get("provider")
    if not provider:
        return jsonify({"error": "provider is required"}), 400

    credentials = data.get("credentials", {})
    config = data.get("config", {})

    try:
        service = BankSyncService(user_id=user_id, provider=provider, config=config)
        result = service.connect(credentials)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/disconnect", methods=["POST"])
@jwt_required()
def disconnect():
    """Disconnect from the current bank provider."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    provider = data.get("provider")
    if not provider:
        return jsonify({"error": "provider is required"}), 400

    try:
        service = BankSyncService(user_id=user_id, provider=provider)
        result = service.disconnect()
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/accounts", methods=["GET"])
@jwt_required()
def list_accounts():
    """List linked bank accounts."""
    user_id = get_jwt_identity()
    provider = request.args.get("provider", "mock")

    try:
        service = BankSyncService(user_id=user_id, provider=provider)
        service.connect({})  # Auto-connect for listing
        accounts = service.list_accounts()
        return jsonify({"accounts": accounts}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/import", methods=["POST"])
@jwt_required()
def import_transactions():
    """
    Import transactions from a bank account.

    JSON body:
        provider: str (required)
        account_id: str (required)
        start_date: str (optional, ISO format)
        end_date: str (optional, ISO format)
    """
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    provider = data.get("provider")
    account_id = data.get("account_id")

    if not provider or not account_id:
        return jsonify({"error": "provider and account_id are required"}), 400

    start_date = None
    end_date = None
    if data.get("start_date"):
        start_date = date.fromisoformat(data["start_date"])
    if data.get("end_date"):
        end_date = date.fromisoformat(data["end_date"])

    try:
        service = BankSyncService(user_id=user_id, provider=provider)
        service.connect({})
        result = service.import_and_save(account_id, start_date, end_date)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/refresh", methods=["POST"])
@jwt_required()
def refresh():
    """
    Refresh account data and import new transactions.

    JSON body:
        provider: str (required)
        account_id: str (optional — refresh specific or all)
    """
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    provider = data.get("provider")
    if not provider:
        return jsonify({"error": "provider is required"}), 400

    account_id = data.get("account_id")

    try:
        service = BankSyncService(user_id=user_id, provider=provider)
        service.connect({})
        result = service.refresh(account_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
