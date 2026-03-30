"""
Bank Connectors API Routes

REST API endpoints for bank connector management.
"""

from datetime import datetime, date, timedelta
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User
from ..services.bank_connectors.base import (
    ConnectorConfig,
    TokenInfo,
    Account,
    Transaction,
    ConnectorStatus,
)
from ..services.bank_connectors.factory import (
    get_connector,
    list_available_connectors,
    get_connector_class,
)
import logging

bp = Blueprint("bank_connectors", __name__)
logger = logging.getLogger("finmind.bank_connectors")


@bp.get("/connectors")
@jwt_required()
def list_connectors():
    """List all available bank connectors"""
    connectors = list_available_connectors()
    return jsonify(connectors)


@bp.get("/connectors/<institution_id>/authorization_url")
@jwt_required()
def get_authorization_url(institution_id: str):
    """Get OAuth authorization URL for a specific connector"""
    uid = int(get_jwt_identity())
    
    connector = get_connector(institution_id)
    if connector is None:
        return jsonify(error="Connector not found"), 404
    
    if not connector.supports_oauth:
        return jsonify(error="This connector does not support OAuth"), 400
    
    # Get redirect URI from request or use default
    redirect_uri = request.args.get("redirect_uri")
    if not redirect_uri:
        # Default redirect URI - in production this would be configured
        redirect_uri = f"{request.host_url}bank/callback"
    
    # Generate state for security
    state = f"{uid}:{institution_id}:{datetime.utcnow().timestamp()}"
    
    auth_url = connector.get_authorization_url(redirect_uri, state)
    
    return jsonify({
        "authorization_url": auth_url,
        "state": state,
        "institution_id": institution_id,
    })


@bp.post("/connectors/<institution_id>/exchange")
@jwt_required()
def exchange_code(institution_id: str):
    """Exchange OAuth authorization code for tokens"""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    code = data.get("code")
    redirect_uri = data.get("redirect_uri")
    
    if not code:
        return jsonify(error="Authorization code required"), 400
    
    connector = get_connector(institution_id)
    if connector is None:
        return jsonify(error="Connector not found"), 404
    
    try:
        token_info = connector.exchange_code(code, redirect_uri or "")
        
        # Store connector configuration in user metadata
        # In a real implementation, you'd store this in a database table
        config = ConnectorConfig(
            user_id=uid,
            institution_id=institution_id,
            access_token=token_info.access_token,
            refresh_token=token_info.refresh_token,
            token_expires_at=token_info.expires_at,
            status=ConnectorStatus.CONNECTED,
        )
        
        logger.info(f"User {uid} connected to {institution_id}")
        
        return jsonify({
            "status": "connected",
            "institution_id": institution_id,
            "institution_name": connector.institution_name,
            "expires_at": token_info.expires_at.isoformat() if token_info.expires_at else None,
        })
        
    except Exception as e:
        logger.error(f"Failed to exchange code for {institution_id}: {e}")
        return jsonify(error=f"Failed to connect: {str(e)}"), 500


@bp.post("/connectors/<institution_id>/refresh")
@jwt_required()
def refresh_token(institution_id: str):
    """Refresh OAuth token for a connected account"""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    current_refresh_token = data.get("refresh_token")
    
    if not current_refresh_token:
        return jsonify(error="Refresh token required"), 400
    
    connector = get_connector(institution_id)
    if connector is None:
        return jsonify(error="Connector not found"), 404
    
    if not connector.supports_refresh:
        return jsonify(error="This connector does not support token refresh"), 400
    
    try:
        # Create token info from current tokens
        token_info = TokenInfo(
            access_token="",  # Will be refreshed
            refresh_token=current_refresh_token,
        )
        
        new_token_info = connector.refresh_token(token_info)
        
        logger.info(f"Refreshed token for user {uid} institution {institution_id}")
        
        return jsonify({
            "status": "refreshed",
            "access_token": new_token_info.access_token,
            "refresh_token": new_token_info.refresh_token,
            "expires_at": new_token_info.expires_at.isoformat() if new_token_info.expires_at else None,
        })
        
    except Exception as e:
        logger.error(f"Failed to refresh token for {institution_id}: {e}")
        return jsonify(error=f"Failed to refresh token: {str(e)}"), 500


@bp.get("/connectors/<institution_id>/accounts")
@jwt_required()
def get_accounts(institution_id: str):
    """Get accounts for a connected institution"""
    uid = int(get_jwt_identity())
    data = request.args.to_dict()
    
    access_token = data.get("access_token")
    
    if not access_token:
        return jsonify(error="Access token required"), 400
    
    connector = get_connector(institution_id)
    if connector is None:
        return jsonify(error="Connector not found"), 404
    
    try:
        token_info = TokenInfo(
            access_token=access_token,
            refresh_token=data.get("refresh_token"),
        )
        
        accounts = connector.get_accounts(token_info)
        
        return jsonify({
            "accounts": [
                {
                    "account_id": acc.account_id,
                    "account_name": acc.account_name,
                    "account_type": acc.account_type,
                    "currency": acc.currency,
                    "balance": float(acc.balance) if acc.balance else None,
                    "available_balance": float(acc.available_balance) if acc.available_balance else None,
                    "mask": acc.mask,
                    "institution_name": acc.institution_name,
                }
                for acc in accounts
            ]
        })
        
    except Exception as e:
        logger.error(f"Failed to get accounts for {institution_id}: {e}")
        return jsonify(error=f"Failed to get accounts: {str(e)}"), 500


@bp.get("/connectors/<institution_id>/transactions")
@jwt_required()
def get_transactions(institution_id: str):
    """Get transactions for a specific account"""
    uid = int(get_jwt_identity())
    data = request.args.to_dict()
    
    access_token = data.get("access_token")
    account_id = data.get("account_id")
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    
    if not access_token:
        return jsonify(error="Access token required"), 400
    if not account_id:
        return jsonify(error="Account ID required"), 400
    
    # Parse dates or use defaults
    try:
        start_date = date.fromisoformat(from_date) if from_date else date.today() - timedelta(days=30)
        end_date = date.fromisoformat(to_date) if to_date else date.today()
    except ValueError:
        return jsonify(error="Invalid date format. Use YYYY-MM-DD"), 400
    
    connector = get_connector(institution_id)
    if connector is None:
        return jsonify(error="Connector not found"), 404
    
    try:
        token_info = TokenInfo(
            access_token=access_token,
            refresh_token=data.get("refresh_token"),
        )
        
        transactions = connector.get_transactions(
            token_info,
            account_id,
            start_date,
            end_date,
        )
        
        return jsonify({
            "transactions": [
                {
                    "transaction_id": tx.transaction_id,
                    "account_id": tx.account_id,
                    "amount": float(tx.amount),
                    "currency": tx.currency,
                    "date": tx.date.isoformat(),
                    "description": tx.description,
                    "merchant_name": tx.merchant_name,
                    "category": tx.category,
                    "pending": tx.pending,
                    "transaction_type": tx.transaction_type,
                }
                for tx in transactions
            ]
        })
        
    except Exception as e:
        logger.error(f"Failed to get transactions for {institution_id}: {e}")
        return jsonify(error=f"Failed to get transactions: {str(e)}"), 500


@bp.post("/connectors/<institution_id>/disconnect")
@jwt_required()
def disconnect(institution_id: str):
    """Disconnect a connected bank account"""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    access_token = data.get("access_token")
    
    connector = get_connector(institution_id)
    if connector is None:
        return jsonify(error="Connector not found"), 404
    
    try:
        token_info = TokenInfo(access_token=access_token) if access_token else None
        connector.disconnect(token_info)
        
        logger.info(f"User {uid} disconnected from {institution_id}")
        
        return jsonify({
            "status": "disconnected",
            "institution_id": institution_id,
        })
        
    except Exception as e:
        logger.error(f"Failed to disconnect {institution_id}: {e}")
        return jsonify(error=f"Failed to disconnect: {str(e)}"), 500


@bp.post("/import/transactions")
@jwt_required()
def import_transactions():
    """Import transactions from bank connector into user expenses"""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    institution_id = data.get("institution_id")
    account_id = data.get("account_id")
    access_token = data.get("access_token")
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    
    # Validation
    if not institution_id:
        return jsonify(error="institution_id required"), 400
    if not account_id:
        return jsonify(error="account_id required"), 400
    if not access_token:
        return jsonify(error="access_token required"), 400
    
    # Parse dates
    try:
        start_date = date.fromisoformat(from_date) if from_date else date.today() - timedelta(days=30)
        end_date = date.fromisoformat(to_date) if to_date else date.today()
    except ValueError:
        return jsonify(error="Invalid date format. Use YYYY-MM-DD"), 400
    
    connector = get_connector(institution_id)
    if connector is None:
        return jsonify(error="Connector not found"), 404
    
    try:
        token_info = TokenInfo(
            access_token=access_token,
            refresh_token=data.get("refresh_token"),
        )
        
        # Get transactions from connector
        transactions = connector.get_transactions(
            token_info,
            account_id,
            start_date,
            end_date,
        )
        
        # Import each transaction as an expense
        from ..models import Expense, Category
        from decimal import Decimal
        
        imported = 0
        skipped = 0
        
        user = db.session.get(User, uid)
        default_currency = user.preferred_currency if user else "USD"
        
        for tx in transactions:
            try:
                # Determine expense type
                expense_type = "INCOME" if tx.transaction_type == "credit" else "EXPENSE"
                
                expense = Expense(
                    user_id=uid,
                    amount=abs(tx.amount),
                    currency=tx.currency or default_currency,
                    expense_type=expense_type,
                    notes=tx.description[:500],
                    spent_at=tx.date,
                    category_id=None,  # Could be mapped from tx.category
                )
                db.session.add(expense)
                imported += 1
            except Exception as e:
                logger.warning(f"Failed to import transaction {tx.transaction_id}: {e}")
                skipped += 1
        
        db.session.commit()
        
        logger.info(
            f"Imported {imported} transactions for user {uid} "
            f"from {institution_id}/{account_id}"
        )
        
        return jsonify({
            "imported": imported,
            "skipped": skipped,
            "total": len(transactions),
        })
        
    except Exception as e:
        logger.error(f"Failed to import transactions: {e}")
        return jsonify(error=f"Failed to import transactions: {str(e)}"), 500
