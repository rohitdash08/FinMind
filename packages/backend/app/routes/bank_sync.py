"""Bank Sync API Routes."""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import BankConnection, BankAccount as BankAccountModel, BankTransaction
from ..connectors import list_connectors, get_connector
from ..connectors.base import ConnectionCredentials

bp = Blueprint('bank_sync', __name__)


@bp.get('/connectors')
@jwt_required()
def get_connectors():
    """List available bank connectors."""
    return jsonify({
        'success': True,
        'data': list_connectors()
    })


@bp.post('/connections')
@jwt_required()
def create_connection():
    """Connect a bank account."""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    connector_id = data.get('connector_id')
    credentials_data = data.get('credentials', {})
    
    if not connector_id:
        return jsonify({'success': False, 'error': 'connector_id required'}), 400
    
    try:
        connector = get_connector(connector_id)
        if not connector:
            return jsonify({'success': False, 'error': 'Connector not found'}), 404
        
        # Connect to bank
        creds = ConnectionCredentials(additional_data=credentials_data)
        result = connector.connect(creds)
        
        # Save connection to database
        connection = BankConnection(
            user_id=user_id,
            connector_id=connector_id,
            connection_id=result['connection_id'],
            institution_name=result.get('institution_name'),
            access_token=result.get('access_token'),
            token_expires_at=result.get('expires_at'),
            status='connected'
        )
        db.session.add(connection)
        db.session.commit()
        
        # Import accounts automatically
        creds.access_token = result['access_token']
        accounts = connector.get_accounts(creds)
        
        for acc in accounts:
            account = BankAccountModel(
                user_id=user_id,
                connection_id=connection.id,
                account_id=acc.id,
                name=acc.name,
                account_type=acc.account_type,
                currency=acc.currency,
                balance=acc.balance,
                masked_number=acc.masked_number
            )
            db.session.add(account)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': {
                'connection': connection.to_dict(),
                'accounts_imported': len(accounts)
            }
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Error connecting bank: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.get('/connections')
@jwt_required()
def get_connections():
    """List user bank connections."""
    user_id = get_jwt_identity()
    connections = BankConnection.query.filter_by(user_id=user_id).all()
    
    return jsonify({
        'success': True,
        'data': [conn.to_dict() for conn in connections]
    })


@bp.get('/connections/<int:connection_id>')
@jwt_required()
def get_connection(connection_id):
    """Get connection details."""
    user_id = get_jwt_identity()
    connection = BankConnection.query.filter_by(
        id=connection_id, user_id=user_id
    ).first()
    
    if not connection:
        return jsonify({'success': False, 'error': 'Connection not found'}), 404
    
    return jsonify({
        'success': True,
        'data': connection.to_dict()
    })


@bp.delete('/connections/<int:connection_id>')
@jwt_required()
def delete_connection(connection_id):
    """Disconnect bank account."""
    user_id = get_jwt_identity()
    connection = BankConnection.query.filter_by(
        id=connection_id, user_id=user_id
    ).first()
    
    if not connection:
        return jsonify({'success': False, 'error': 'Connection not found'}), 404
    
    try:
        # Disconnect from bank
        connector = get_connector(connection.connector_id)
        if connector and connection.access_token:
            creds = ConnectionCredentials(access_token=connection.access_token)
            connector.disconnect(creds)
        
        # Delete from database
        db.session.delete(connection)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Connection deleted'})
        
    except Exception as e:
        current_app.logger.error(f"Error disconnecting: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.post('/connections/<int:connection_id>/sync')
@jwt_required()
def sync_connection(connection_id):
    """Sync transactions for a connection."""
    user_id = get_jwt_identity()
    connection = BankConnection.query.filter_by(
        id=connection_id, user_id=user_id
    ).first()
    
    if not connection:
        return jsonify({'success': False, 'error': 'Connection not found'}), 404
    
    data = request.get_json() or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    # Parse dates
    if start_date:
        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    else:
        start_date = datetime.utcnow() - timedelta(days=30)
    
    if end_date:
        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    else:
        end_date = datetime.utcnow()
    
    try:
        connector = get_connector(connection.connector_id)
        if not connector:
            return jsonify({'success': False, 'error': 'Connector not found'}), 404
        
        creds = ConnectionCredentials(access_token=connection.access_token)
        
        # Refresh token if needed
        if connection.token_expires_at and connection.token_expires_at < datetime.utcnow():
            creds = connector.refresh_connection(creds)
            connection.access_token = creds.access_token
            connection.token_expires_at = creds.expires_at
        
        # Get accounts
        accounts = BankAccountModel.query.filter_by(
            connection_id=connection.id, user_id=user_id
        ).all()
        
        total_imported = 0
        
        for account in accounts:
            transactions = connector.get_transactions(
                creds, account.account_id, start_date, end_date
            )
            
            for txn in transactions:
                # Check if transaction already exists
                existing = BankTransaction.query.filter_by(
                    transaction_id=txn.id, account_id=account.id
                ).first()
                
                if existing:
                    continue
                
                new_txn = BankTransaction(
                    user_id=user_id,
                    account_id=account.id,
                    transaction_id=txn.id,
                    amount=txn.amount,
                    currency=txn.currency,
                    description=txn.description,
                    merchant_name=txn.merchant_name,
                    transaction_date=txn.transaction_date.date(),
                    pending=txn.pending
                )
                db.session.add(new_txn)
                total_imported += 1
            
            account.last_sync_at = datetime.utcnow()
        
        connection.last_sync_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': {
                'transactions_imported': total_imported,
                'synced_at': datetime.utcnow().isoformat()
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error syncing: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.get('/connections/<int:connection_id>/accounts')
@jwt_required()
def get_connection_accounts(connection_id):
    """Get accounts for a connection."""
    user_id = get_jwt_identity()
    accounts = BankAccountModel.query.filter_by(
        connection_id=connection_id
    ).join(BankConnection).filter(BankConnection.user_id == user_id).all()
    
    return jsonify({
        'success': True,
        'data': [acc.to_dict() for acc in accounts]
    })


@bp.get('/accounts/<int:account_id>/transactions')
@jwt_required()
def get_account_transactions(account_id):
    """Get transactions for an account."""
    user_id = get_jwt_identity()
    
    account = BankAccountModel.query.filter_by(
        id=account_id
    ).join(BankConnection).filter(BankConnection.user_id == user_id).first()
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    
    transactions = BankTransaction.query.filter_by(
        account_id=account_id
    ).order_by(BankTransaction.transaction_date.desc()).all()
    
    return jsonify({
        'success': True,
        'data': [txn.to_dict() for txn in transactions]
    })
