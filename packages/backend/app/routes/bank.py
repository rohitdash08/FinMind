"""
Bank sync API routes.

Provides endpoints for connecting banks, importing transactions, etc.
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from .extensions import db
from .models_bank import BankConnection, BankTransactionImport
from .services.bank_connector import (
    get_connector,
    BaseBankConnector,
    ConnectionStatus,
    CONNECTOR_REGISTRY,
)

bp = Blueprint("bank", __name__, url_prefix="/api/bank")
logger = logging.getLogger("finmind.bank")


@bp.get("/connectors")
@jwt_required()
def list_connectors():
    """List available bank connector types."""
    return jsonify({
        "connectors": [
            {
                "type": ctype,
                "name": ctype.title(),
                "description": f"{ctype.title()} Bank Connector"
            }
            for ctype in CONNECTOR_REGISTRY.keys()
        ]
    })


@bp.get("/connections")
@jwt_required()
def list_connections():
    """List user's bank connections."""
    uid = int(get_jwt_identity())
    connections = db.session.query(BankConnection).filter_by(user_id=uid).all()
    
    return jsonify([
        {
            "id": c.id,
            "connector_type": c.connector_type,
            "institution_name": c.institution_name,
            "account_name": c.account_name,
            "status": c.status,
            "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
            "created_at": c.created_at.isoformat()
        }
        for c in connections
    ])


@bp.post("/connect")
@jwt_required()
def connect_bank():
    """
    Connect to a bank account.
    
    Request body:
        - connector_type: Type of connector (e.g., 'mock')
        - config: Configuration for the connector
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    connector_type = data.get("connector_type", "mock")
    config = data.get("config", {})
    
    try:
        # Get connector instance
        connector = get_connector(connector_type, config)
        
        # Connect to bank
        if not connector.connect():
            return jsonify(error="Failed to connect to bank"), 400
        
        if connector.status != ConnectionStatus.CONNECTED:
            return jsonify(error=connector.last_error or "Connection failed"), 400
        
        # Get accounts
        accounts = connector.get_accounts()
        
        # Save connections for each account
        created_connections = []
        for account in accounts:
            connection = BankConnection(
                user_id=uid,
                connector_type=connector_type,
                institution_name=account.institution_name,
                account_name=account.account_name,
                external_account_id=account.account_id,
                status="connected",
                last_sync_at=datetime.utcnow()
            )
            db.session.add(connection)
            created_connections.append(connection)
        
        db.session.commit()
        
        logger.info(f"User {uid} connected to {len(created_connections)} accounts")
        
        return jsonify({
            "message": "Connected successfully",
            "connections": [
                {
                    "id": c.id,
                    "account_name": c.account_name,
                    "institution_name": c.institution_name
                }
                for c in created_connections
            ]
        }), 201
        
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        logger.error(f"Error connecting bank: {e}")
        return jsonify(error="Internal error"), 500


@bp.delete("/connections/<int:connection_id>")
@jwt_required()
def disconnect_bank(connection_id: int):
    """Disconnect a bank connection."""
    uid = int(get_jwt_identity())
    
    connection = db.session.query(BankConnection).filter_by(
        id=connection_id, user_id=uid
    ).first()
    
    if not connection:
        return jsonify(error="Connection not found"), 404
    
    try:
        # Get connector and disconnect
        connector = get_connector(connection.connector_type, {})
        connector.disconnect()
    except Exception as e:
        logger.warning(f"Error disconnecting connector: {e}")
    
    # Update status
    connection.status = "disconnected"
    db.session.commit()
    
    return jsonify(message="Disconnected successfully")


@bp.post("/connections/<int:connection_id>/sync")
@jwt_required()
def sync_transactions(connection_id: int):
    """
    Sync transactions from a bank connection.
    
    Optional query params:
        - days: Number of days to look back (default: 30)
    """
    uid = int(get_jwt_identity())
    days = request.args.get("days", 30, type=int)
    
    connection = db.session.query(BankConnection).filter_by(
        id=connection_id, user_id=uid
    ).first()
    
    if not connection:
        return jsonify(error="Connection not found"), 404
    
    if connection.status != "connected":
        return jsonify(error="Connection is not active"), 400
    
    try:
        # Get connector
        connector = get_connector(connection.connector_type, {})
        
        # Refresh if needed
        if not connector.refresh():
            return jsonify(error="Failed to refresh connection"), 400
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get transactions
        transactions = connector.get_transactions(
            connection.external_account_id,
            start_date=start_date,
            end_date=end_date
        )
        
        # Import new transactions
        imported_count = 0
        for txn in transactions:
            # Check if already imported
            existing = db.session.query(BankTransactionImport).filter_by(
                connection_id=connection.id,
                external_transaction_id=txn.external_id
            ).first()
            
            if not existing:
                # Create import record
                import_record = BankTransactionImport(
                    connection_id=connection.id,
                    external_transaction_id=txn.external_id,
                    amount=txn.amount,
                    currency=txn.currency
                )
                db.session.add(import_record)
                imported_count += 1
        
        # Update last sync time
        connection.last_sync_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(
            f"Synced {len(transactions)} transactions for user {uid}, "
            f"imported {imported_count} new"
        )
        
        return jsonify({
            "message": "Sync completed",
            "total_transactions": len(transactions),
            "new_transactions": imported_count,
            "last_sync": connection.last_sync_at.isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error syncing transactions: {e}")
        return jsonify(error="Sync failed"), 500


@bp.get("/connections/<int:connection_id>/transactions")
@jwt_required()
def get_transactions(connection_id: int):
    """Get imported transactions for a connection."""
    uid = int(get_jwt_identity())
    
    connection = db.session.query(BankConnection).filter_by(
        id=connection_id, user_id=uid
    ).first()
    
    if not connection:
        return jsonify(error="Connection not found"), 404
    
    # Get import records
    imports = db.session.query(BankTransactionImport).filter_by(
        connection_id=connection_id
    ).order_by(BankTransactionImport.imported_at.desc()).limit(100).all()
    
    return jsonify([
        {
            "external_id": i.external_transaction_id,
            "amount": float(i.amount),
            "currency": i.currency,
            "imported_at": i.imported_at.isoformat()
        }
        for i in imports
    ])
