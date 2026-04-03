"""Routes for Bank Sync Connector Architecture (issue #75)."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.bank_sync import (
    create_connector,
    list_connectors,
    get_connector_class,
    SyncResult,
)

bp = Blueprint("bank_sync", __name__)


@bp.route("/bank-sync/connectors", methods=["GET"])
def get_connectors():
    """List all available bank connectors."""
    connectors = list_connectors()
    return jsonify({"connectors": connectors, "count": len(connectors)}), 200


@bp.route("/bank-sync/validate", methods=["POST"])
@jwt_required()
def validate_connector():
    """Validate connector credentials without importing data."""
    data = request.get_json() or {}
    connector_name = data.get("connector")
    credentials = data.get("credentials", {})

    if not connector_name:
        return jsonify({"error": "connector name is required"}), 400

    connector = create_connector(connector_name, credentials, data.get("options", {}))
    if not connector:
        return jsonify({"error": f"Unknown connector: {connector_name}"}), 404

    is_valid = connector.validate_credentials()
    return jsonify({
        "connector": connector_name,
        "valid": is_valid,
        "message": "Credentials valid" if is_valid else "Invalid credentials",
    }), 200


@bp.route("/bank-sync/import", methods=["POST"])
@jwt_required()
def import_transactions():
    """Import transactions using the specified connector."""
    data = request.get_json() or {}
    connector_name = data.get("connector")
    account_id = data.get("account_id", "default")
    credentials = data.get("credentials", {})
    options = data.get("options", {})

    if not connector_name:
        return jsonify({"error": "connector name is required"}), 400

    connector = create_connector(connector_name, credentials, options)
    if not connector:
        return jsonify({"error": f"Unknown connector: {connector_name}"}), 404

    if not connector.validate_credentials():
        return jsonify({"error": "Invalid credentials for connector"}), 401

    # Parse optional date filters
    since = None
    until = None
    try:
        from datetime import date as date_cls
        if data.get("since"):
            since = date_cls.fromisoformat(data["since"])
        if data.get("until"):
            until = date_cls.fromisoformat(data["until"])
    except ValueError as e:
        return jsonify({"error": f"Invalid date format: {e}"}), 400

    result = connector.refresh(account_id)
    return jsonify(result.to_dict()), 200 if result.success else 500


@bp.route("/bank-sync/balance", methods=["POST"])
@jwt_required()
def get_account_balance():
    """Get current account balance via connector."""
    data = request.get_json() or {}
    connector_name = data.get("connector")
    account_id = data.get("account_id", "default")
    credentials = data.get("credentials", {})

    if not connector_name:
        return jsonify({"error": "connector name is required"}), 400

    connector = create_connector(connector_name, credentials, data.get("options", {}))
    if not connector:
        return jsonify({"error": f"Unknown connector: {connector_name}"}), 404

    cls = connector.__class__
    if not cls.SUPPORTS_BALANCE:
        return jsonify({
            "error": f"Connector '{connector_name}' does not support balance queries"
        }), 400

    balance = connector.get_balance(account_id)
    return jsonify({
        "connector": connector_name,
        "account_id": account_id,
        "balance": str(balance) if balance is not None else None,
        "currency": credentials.get("currency", "USD"),
    }), 200