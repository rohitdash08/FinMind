"""Bank Sync Service.

This module provides the main service for syncing bank data,
orchestrating between connectors and the database.
"""

import logging
from datetime import date, datetime
from typing import Any, Optional

from ..extensions import db
from ..models import Expense
from .bank_connector import (
    BankConnector,
    BankConnectionStatus,
    ConnectorRegistry,
    SyncResult,
)
from .bank_connectors.mock import MockBankConnector

logger = logging.getLogger("finmind.bank_sync")


class BankSyncService:
    """Service for syncing bank data.
    
    This service orchestrates bank connections, account syncing,
    and transaction import.
    
    Example:
        >>> service = BankSyncService()
        >>> # Connect to a bank
        >>> connector = service.connect_bank("mock", {"api_key": "test"})
        >>> # Sync accounts
        >>> result = service.sync_accounts(user_id=1, connector=connector)
        >>> # Sync transactions
        >>> tx_result = service.sync_transactions(
        ...     user_id=1,
        ...     connector=connector,
        ...     account_id="mock_acc_0"
        ... )
    """
    
    def __init__(self):
        self.registry = ConnectorRegistry()
    
    def connect_bank(
        self,
        connector_id: str,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None
    ) -> Optional[BankConnector]:
        """Connect to a bank using the specified connector.
        
        Args:
            connector_id: The connector identifier (e.g., "mock")
            credentials: Authentication credentials
            config: Optional additional configuration
            
        Returns:
            Connected BankConnector or None if connection failed
        """
        config = config or {}
        
        # Create connector instance
        connector = self.registry.create_connector(connector_id, config)
        if not connector:
            logger.error(f"Unknown connector: {connector_id}")
            return None
        
        # Authenticate
        if not connector.authenticate(credentials):
            logger.error(f"Authentication failed for connector: {connector_id}")
            return None
        
        logger.info(f"Successfully connected to {connector_id}")
        return connector
    
    def sync_accounts(
        self,
        user_id: int,
        connector: BankConnector
    ) -> SyncResult:
        """Sync bank accounts for a user.
        
        Args:
            user_id: The user ID
            connector: The authenticated bank connector
            
        Returns:
            SyncResult with account information
        """
        result = SyncResult(success=False)
        
        if not connector.is_authenticated():
            result.errors.append("Connector not authenticated")
            return result
        
        try:
            accounts = connector.fetch_accounts()
            result.accounts_synced = len(accounts)
            result.success = True
            result.last_sync_at = datetime.utcnow()
            
            logger.info(
                f"Synced {len(accounts)} accounts for user {user_id}"
            )
        except Exception as e:
            result.errors.append(f"Failed to fetch accounts: {str(e)}")
            logger.exception("Account sync failed")
        
        return result
    
    def sync_transactions(
        self,
        user_id: int,
        connector: BankConnector,
        account_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        import_to_expenses: bool = True
    ) -> SyncResult:
        """Sync transactions from a bank account.
        
        Args:
            user_id: The user ID
            connector: The authenticated bank connector
            account_id: The bank account ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            import_to_expenses: Whether to import transactions as expenses
            
        Returns:
            SyncResult with transaction information
        """
        result = SyncResult(success=False)
        
        if not connector.is_authenticated():
            result.errors.append("Connector not authenticated")
            return result
        
        try:
            transactions = connector.fetch_transactions(
                account_id=account_id,
                start_date=start_date,
                end_date=end_date
            )
            
            result.transactions_synced = len(transactions)
            result.new_transactions = transactions
            
            # Import to expenses if requested
            if import_to_expenses:
                imported_count = self._import_transactions_to_expenses(
                    user_id, transactions
                )
                logger.info(
                    f"Imported {imported_count} transactions as expenses "
                    f"for user {user_id}"
                )
            
            result.success = True
            result.last_sync_at = datetime.utcnow()
            
            logger.info(
                f"Synced {len(transactions)} transactions from account "
                f"{account_id} for user {user_id}"
            )
        except Exception as e:
            result.errors.append(f"Failed to fetch transactions: {str(e)}")
            logger.exception("Transaction sync failed")
        
        return result
    
    def _import_transactions_to_expenses(
        self,
        user_id: int,
        transactions: list
    ) -> int:
        """Import bank transactions as expenses.
        
        Args:
            user_id: The user ID
            transactions: List of bank transactions
            
        Returns:
            Number of transactions imported
        """
        imported = 0
        
        for tx in transactions:
            # Skip positive amounts (income) for expense import
            # or handle them differently
            expense_type = "EXPENSE" if tx.amount < 0 else "INCOME"
            
            # Check for duplicates
            existing = Expense.query.filter_by(
                user_id=user_id,
                spent_at=tx.date,
                amount=abs(tx.amount),
                notes=tx.description
            ).first()
            
            if existing:
                continue
            
            expense = Expense(
                user_id=user_id,
                amount=abs(tx.amount),
                currency=tx.currency,
                expense_type=expense_type,
                notes=tx.description,
                spent_at=tx.date,
            )
            db.session.add(expense)
            imported += 1
        
        if imported > 0:
            db.session.commit()
        
        return imported
    
    def refresh_connection(self, connector: BankConnector) -> bool:
        """Refresh a bank connection.
        
        Args:
            connector: The bank connector to refresh
            
        Returns:
            True if refresh successful
        """
        return connector.refresh()
    
    def disconnect_bank(self, connector: BankConnector) -> bool:
        """Disconnect from a bank.
        
        Args:
            connector: The bank connector to disconnect
            
        Returns:
            True if disconnected successfully
        """
        return connector.disconnect()
    
    def get_connector_status(
        self,
        connector: BankConnector
    ) -> dict[str, Any]:
        """Get detailed connector status.
        
        Args:
            connector: The bank connector
            
        Returns:
            Status information dictionary
        """
        return {
            "connector_id": connector.connector_id,
            "name": connector.name,
            "authenticated": connector.is_authenticated(),
            "connection_status": connector.get_connection_status().value,
            "health": connector.health_check(),
        }
    
    def list_available_connectors(self) -> dict[str, str]:
        """List all available bank connectors.
        
        Returns:
            Dictionary of connector_id -> connector_name
        """
        connectors = self.registry.list_connectors()
        return {
            cid: cls.__name__ 
            for cid, cls in connectors.items()
        }
