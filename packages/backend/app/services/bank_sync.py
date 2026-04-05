"""
Bank Sync Service

Service for managing bank connector connections and syncing transactions.
"""

import logging
from datetime import date, datetime
from typing import Any

from ..extensions import db
from ..models import Expense, User
from .bank_connector import (
    BankConnector,
    BankTransaction,
    ConnectorConfig,
    ConnectorRegistry,
)

logger = logging.getLogger("finmind.bank_sync")


class BankSyncService:
    """
    Service for managing bank connector operations.
    
    Handles connection lifecycle, transaction import, and refresh.
    """
    
    @staticmethod
    def list_available_connectors() -> list[dict[str, Any]]:
        """List all available bank connectors."""
        return ConnectorRegistry.list_connectors()
    
    @staticmethod
    def get_connector(connector_type: str) -> BankConnector | None:
        """Get a connector instance by type."""
        return ConnectorRegistry.get_connector(connector_type)
    
    @staticmethod
    def connect(
        user_id: int,
        connector_type: str,
        credentials: dict[str, str],
    ) -> dict[str, Any]:
        """
        Connect a user to a bank connector.
        
        Args:
            user_id: The user's ID
            connector_type: Type of connector to connect
            credentials: Credentials for the connector
            
        Returns:
            Connection result with status
        """
        connector = ConnectorRegistry.get_connector(connector_type)
        if not connector:
            return {
                "success": False,
                "error": f"Unknown connector type: {connector_type}",
            }
        
        # Validate credentials
        if not connector.validate_credentials(credentials):
            return {
                "success": False,
                "error": "Invalid credentials",
            }
        
        # Create config and connect
        config = ConnectorConfig(
            connector_type=connector_type,
            user_id=user_id,
            credentials=credentials,
        )
        
        try:
            success = connector.connect(config)
            if success:
                # Get accounts
                accounts = connector.get_accounts()
                logger.info(
                    "Connected user %s to %s connector with %d accounts",
                    user_id,
                    connector_type,
                    len(accounts),
                )
                return {
                    "success": True,
                    "connector_type": connector_type,
                    "display_name": connector.display_name,
                    "accounts": [
                        {
                            "account_id": a.account_id,
                            "account_name": a.account_name,
                            "account_type": a.account_type,
                            "currency": a.currency,
                            "current_balance": a.current_balance,
                        }
                        for a in accounts
                    ],
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to connect to bank",
                }
        except Exception as e:
            logger.error(
                "Error connecting user %s to %s: %s",
                user_id,
                connector_type,
                str(e),
            )
            return {
                "success": False,
                "error": f"Connection error: {str(e)}",
            }
    
    @staticmethod
    def disconnect(connector_type: str) -> dict[str, Any]:
        """
        Disconnect from a bank connector.
        
        Args:
            connector_type: Type of connector to disconnect
            
        Returns:
            Disconnection result
        """
        connector = ConnectorRegistry.get_connector(connector_type)
        if not connector:
            return {
                "success": False,
                "error": f"Unknown connector type: {connector_type}",
            }
        
        try:
            connector.disconnect()
            return {"success": True}
        except Exception as e:
            logger.error("Error disconnecting %s: %s", connector_type, str(e))
            return {
                "success": False,
                "error": f"Disconnect error: {str(e)}",
            }
    
    @staticmethod
    def get_connection_status(connector_type: str) -> dict[str, Any]:
        """Get the connection status for a connector."""
        connector = ConnectorRegistry.get_connector(connector_type)
        if not connector:
            return {
                "connected": False,
                "error": f"Unknown connector type: {connector_type}",
            }
        return connector.get_connection_status()
    
    @staticmethod
    def import_transactions(
        user_id: int,
        connector_type: str,
        account_id: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> dict[str, Any]:
        """
        Import transactions from a connected bank account.
        
        Args:
            user_id: The user's ID
            connector_type: Type of connector
            account_id: Account to import from
            from_date: Start date for import
            to_date: End date for import
            
        Returns:
            Import result with transactions
        """
        connector = ConnectorRegistry.get_connector(connector_type)
        if not connector:
            return {
                "success": False,
                "error": f"Unknown connector type: {connector_type}",
            }
        
        try:
            transactions = connector.get_transactions(
                account_id,
                from_date=from_date,
                to_date=to_date,
            )
            
            logger.info(
                "Imported %d transactions for user %s from %s",
                len(transactions),
                user_id,
                connector_type,
            )
            
            return {
                "success": True,
                "total": len(transactions),
                "transactions": [
                    {
                        "date": tx.date.isoformat(),
                        "amount": tx.amount,
                        "description": tx.description,
                        "expense_type": (
                            "INCOME"
                            if tx.transaction_type.value in ("CREDIT", "INCOME")
                            else "EXPENSE"
                        ),
                        "currency": tx.currency,
                        "category_id": tx.category_id,
                        "external_id": tx.external_id,
                    }
                    for tx in transactions
                ],
            }
        except Exception as e:
            logger.error(
                "Error importing transactions for user %s: %s",
                user_id,
                str(e),
            )
            return {
                "success": False,
                "error": f"Import error: {str(e)}",
            }
    
    @staticmethod
    def refresh_transactions(
        user_id: int,
        connector_type: str,
        account_id: str,
        since: datetime,
    ) -> dict[str, Any]:
        """
        Refresh new transactions from a connected account.
        
        Args:
            user_id: The user's ID
            connector_type: Type of connector
            account_id: Account to refresh
            since: Only get transactions newer than this
            
        Returns:
            Refresh result with new transactions
        """
        connector = ConnectorRegistry.get_connector(connector_type)
        if not connector:
            return {
                "success": False,
                "error": f"Unknown connector type: {connector_type}",
            }
        
        try:
            transactions = connector.refresh_transactions(account_id, since)
            
            logger.info(
                "Refreshed %d new transactions for user %s from %s",
                len(transactions),
                user_id,
                connector_type,
            )
            
            return {
                "success": True,
                "new_count": len(transactions),
                "transactions": [
                    {
                        "date": tx.date.isoformat(),
                        "amount": tx.amount,
                        "description": tx.description,
                        "expense_type": (
                            "INCOME"
                            if tx.transaction_type.value in ("CREDIT", "INCOME")
                            else "EXPENSE"
                        ),
                        "currency": tx.currency,
                        "category_id": tx.category_id,
                        "external_id": tx.external_id,
                    }
                    for tx in transactions
                ],
            }
        except Exception as e:
            logger.error(
                "Error refreshing transactions for user %s: %s",
                user_id,
                str(e),
            )
            return {
                "success": False,
                "error": f"Refresh error: {str(e)}",
            }
    
    @staticmethod
    def commit_transactions(
        user_id: int,
        transactions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Commit imported transactions to the database.
        
        Args:
            user_id: The user's ID
            transactions: List of transaction dicts to save
            
        Returns:
            Commit result with inserted/duplicate counts
        """
        user = db.session.get(User, user_id)
        if not user:
            return {
                "success": False,
                "error": "User not found",
            }
        
        inserted = 0
        duplicates = 0
        errors = 0
        
        for tx_data in transactions:
            try:
                # Check for duplicate by date, amount, and description
                existing = (
                    db.session.query(Expense)
                    .filter_by(
                        user_id=user_id,
                        spent_at=date.fromisoformat(tx_data["date"]),
                        amount=tx_data["amount"],
                    )
                    .filter(Expense.notes.ilike(f"%{tx_data['description']}%"))
                    .first()
                )
                
                if existing:
                    duplicates += 1
                    continue
                
                expense = Expense(
                    user_id=user_id,
                    amount=tx_data["amount"],
                    currency=tx_data.get("currency", user.preferred_currency)[:10],
                    expense_type=tx_data.get("expense_type", "EXPENSE").upper(),
                    category_id=tx_data.get("category_id"),
                    notes=tx_data.get("description", "")[:500],
                    spent_at=date.fromisoformat(tx_data["date"]),
                )
                db.session.add(expense)
                inserted += 1
                
            except Exception as e:
                logger.warning(
                    "Error processing transaction for user %s: %s",
                    user_id,
                    str(e),
                )
                errors += 1
        
        try:
            db.session.commit()
            logger.info(
                "Committed %d transactions for user %s (%d duplicates, %d errors)",
                inserted,
                user_id,
                duplicates,
                errors,
            )
            return {
                "success": True,
                "inserted": inserted,
                "duplicates": duplicates,
                "errors": errors,
            }
        except Exception as e:
            db.session.rollback()
            logger.error(
                "Error committing transactions for user %s: %s",
                user_id,
                str(e),
            )
            return {
                "success": False,
                "error": f"Commit error: {str(e)}",
                "inserted": inserted,
                "duplicates": duplicates,
                "errors": errors,
            }
    
    @staticmethod
    def get_accounts(connector_type: str) -> list[dict[str, Any]]:
        """Get accounts from a connected connector."""
        connector = ConnectorRegistry.get_connector(connector_type)
        if not connector:
            return []
        
        try:
            accounts = connector.get_accounts()
            return [
                {
                    "account_id": a.account_id,
                    "account_name": a.account_name,
                    "account_type": a.account_type,
                    "currency": a.currency,
                    "current_balance": a.current_balance,
                    "available_balance": a.available_balance,
                }
                for a in accounts
            ]
        except Exception as e:
            logger.error("Error getting accounts from %s: %s", connector_type, str(e))
            return []