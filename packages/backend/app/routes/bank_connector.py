"""
Bank Connector Routes - API endpoints for bank integrations.

Provides endpoints for:
- Listing connected bank accounts
- Importing transactions from connected accounts
- Refreshing account balances
"""

import logging
from datetime import date
from typing import Any

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.bank_connectors import (
    get_connector,
    ConnectorType,
    BankAccount,
    Transaction,
)

bp = Blueprint("bank_connector", __name__)
logger = logging.getLogger("finmind.bank_connector")


def serialize_account(account: BankAccount) -> dict[str, Any]:
    """Serialize a BankAccount to JSON."""
    return {
        "account_id": account.account_id,
        "account_name": account.account_name,
        "account_type": account.account_type,
        "balance": str(account.balance),
        "currency": account.currency,
        "institution_name": account.institution_name,
        "last_updated": account.last_updated.isoformat(),
    }


def serialize_transaction(tx: Transaction) -> dict[str, Any]:
    """Serialize a Transaction to JSON."""
    return {
        "transaction_id": tx.transaction_id,
        "account_id": tx.account_id,
        "amount": str(tx.amount),
        "currency": tx.currency,
        "date": tx.date.isoformat(),
        "description": tx.description,
        "category": tx.category,
        "merchant_name": tx.merchant_name,
    }


@bp.get("/accounts")
@jwt_required()
def list_accounts():
    """
    List all connected bank accounts.
    
    Query parameters:
        connector_type: Type of connector (default: mock)
        api_key: API key for the connector (optional for mock)
    """
    uid = int(get_jwt_identity())
    connector_type = request.args.get("connector_type", "mock")
    api_key = request.args.get("api_key")
    
    try:
        connector = get_connector(connector_type, api_key)
        accounts = connector.get_accounts()
        
        logger.info("List accounts user=%s connector=%s count=%s", 
                    uid, connector_type, len(accounts))
        
        return jsonify({
            "accounts": [serialize_account(acc) for acc in accounts],
            "connector_type": connector_type,
        })
    except ValueError as e:
        logger.warning("Invalid connector type: %s", e)
        return jsonify(error=str(e)), 400
    except Exception as e:
        logger.error("Failed to get accounts: %s", e)
        return jsonify(error="Failed to fetch accounts"), 500


@bp.get("/accounts/<account_id>/transactions")
@jwt_required()
def get_transactions(account_id: str):
    """
    Get transactions for a specific account.
    
    Query parameters:
        connector_type: Type of connector (default: mock)
        api_key: API key for the connector (optional for mock)
        start_date: Start date (YYYY-MM-DD, optional)
        end_date: End date (YYYY-MM-DD, optional)
    """
    uid = int(get_jwt_identity())
    connector_type = request.args.get("connector_type", "mock")
    api_key = request.args.get("api_key")
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")
    
    # Parse dates
    start_date = None
    end_date = None
    try:
        if start_date_str:
            start_date = date.fromisoformat(start_date_str)
        if end_date_str:
            end_date = date.fromisoformat(end_date_str)
    except ValueError:
        return jsonify(error="Invalid date format. Use YYYY-MM-DD"), 400
    
    try:
        connector = get_connector(connector_type, api_key)
        transactions = connector.get_transactions(
            account_id, 
            start_date=start_date,
            end_date=end_date,
        )
        
        logger.info("Get transactions user=%s account=%s count=%s", 
                    uid, account_id, len(transactions))
        
        return jsonify({
            "transactions": [serialize_transaction(tx) for tx in transactions],
            "account_id": account_id,
        })
    except ValueError as e:
        logger.warning("Error: %s", e)
        return jsonify(error=str(e)), 400
    except Exception as e:
        logger.error("Failed to get transactions: %s", e)
        return jsonify(error="Failed to fetch transactions"), 500


@bp.post("/accounts/<account_id>/refresh")
@jwt_required()
def refresh_account(account_id: str):
    """
    Refresh a specific account's balance.
    
    Query parameters:
        connector_type: Type of connector (default: mock)
        api_key: API key for the connector (optional for mock)
    """
    uid = int(get_jwt_identity())
    connector_type = request.args.get("connector_type", "mock")
    api_key = request.args.get("api_key")
    
    try:
        connector = get_connector(connector_type, api_key)
        account = connector.refresh_account(account_id)
        
        logger.info("Refresh account user=%s account=%s", uid, account_id)
        
        return jsonify(serialize_account(account))
    except ValueError as e:
        logger.warning("Error refreshing account: %s", e)
        return jsonify(error=str(e)), 400
    except Exception as e:
        logger.error("Failed to refresh account: %s", e)
        return jsonify(error="Failed to refresh account"), 500


@bp.get("/connectors")
@jwt_required()
def list_connectors():
    """List available connector types."""
    return jsonify({
        "connectors": [
            {
                "type": ct.value,
                "name": ct.name,
                "description": _get_connector_description(ct),
            }
            for ct in ConnectorType
        ]
    })


def _get_connector_description(connector_type: ConnectorType) -> str:
    """Get description for a connector type."""
    descriptions = {
        ConnectorType.MOCK: "Mock connector for testing and development",
        ConnectorType.PLAID: "Plaid - Connect to US banks",
        ConnectorType.MONZO: "Monzo - UK bank integration",
        ConnectorType.REVOLUT: "Revolut - Multi-currency account",
    }
    return descriptions.get(connector_type, "Unknown connector")


@bp.post("/test-connection")
@jwt_required()
def test_connection():
    """
    Test connection to a bank API.
    
    Query parameters:
        connector_type: Type of connector
        api_key: API key for the connector
    """
    connector_type = request.args.get("connector_type", "mock")
    api_key = request.args.get("api_key")
    
    try:
        connector = get_connector(connector_type, api_key)
        success = connector.test_connection()
        
        return jsonify({
            "connected": success,
            "connector_type": connector_type,
        })
    except Exception as e:
        logger.error("Connection test failed: %s", e)
        return jsonify(error="Connection test failed"), 500