"""
Mock Bank Connector

A mock connector for testing and development purposes.
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
import random
import logging
from .base import (
    BaseBankConnector,
    ConnectorConfig,
    TokenInfo,
    Account,
    Transaction,
)
from .factory import register_connector

logger = logging.getLogger("finmind.bank_connectors.mock")


@register_connector
class MockBankConnector(BaseBankConnector):
    """
    Mock bank connector for testing and development.
    
    This connector simulates a real bank API without making actual network calls.
    Useful for development, testing, and demo purposes.
    """
    
    INSTITUTION_ID = "mock_bank"
    INSTITUTION_NAME = "Mock Bank (Test)"
    SUPPORTS_OAUTH = True
    SUPPORTS_REFRESH = True
    
    # Mock data configuration
    DEFAULT_ACCOUNT_COUNT = 2
    DEFAULT_TRANSACTION_COUNT = 20
    
    def __init__(self, config: ConnectorConfig | None = None):
        super().__init__(config)
        self._mock_accounts: list[Account] = []
        self._mock_transactions: dict[str, list[Transaction]] = {}
        self._connected = False
    
    @property
    def institution_id(self) -> str:
        return self.INSTITUTION_ID
    
    @property
    def institution_name(self) -> str:
        return self.INSTITUTION_NAME
    
    @property
    def supports_oauth(self) -> bool:
        return self.SUPPORTS_OAUTH
    
    @property
    def supports_refresh(self) -> bool:
        return self.SUPPORTS_REFRESH
    
    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Get mock OAuth authorization URL"""
        # In a real implementation, this would redirect to the bank's OAuth flow
        # For mock purposes, we simulate the flow
        self._logger.info(f"Mock OAuth flow initiated with state: {state}")
        return f"{redirect_uri}?state={state}&code=mock_auth_code_{random.randint(1000, 9999)}"
    
    def exchange_code(self, code: str, redirect_uri: str) -> TokenInfo:
        """Exchange mock authorization code for tokens"""
        self._logger.info(f"Exchanging mock code: {code}")
        
        # Simulate token exchange
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        return TokenInfo(
            access_token=f"mock_access_token_{random.randint(10000, 99999)}",
            refresh_token=f"mock_refresh_token_{random.randint(10000, 99999)}",
            expires_at=expires_at,
            token_type="Bearer",
            scope="transactions:read accounts:read",
        )
    
    def refresh_token(self, token_info: TokenInfo) -> TokenInfo:
        """Refresh mock token"""
        self._logger.info("Refreshing mock token")
        
        # Simulate token refresh
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        return TokenInfo(
            access_token=f"mock_access_token_{random.randint(10000, 99999)}",
            refresh_token=token_info.refresh_token,
            expires_at=expires_at,
            token_type="Bearer",
            scope=token_info.scope,
        )
    
    def get_accounts(self, token_info: TokenInfo) -> list[Account]:
        """Get mock accounts"""
        self._logger.info("Fetching mock accounts")
        
        if not self._mock_accounts:
            self._generate_mock_accounts()
        
        return self._mock_accounts
    
    def get_transactions(
        self,
        token_info: TokenInfo,
        account_id: str,
        start_date: date,
        end_date: date,
    ) -> list[Transaction]:
        """Get mock transactions"""
        self._logger.info(
            f"Fetching mock transactions for account {account_id} "
            f"from {start_date} to {end_date}"
        )
        
        # Generate transactions if not exist
        if account_id not in self._mock_transactions:
            self._generate_mock_transactions(account_id)
        
        # Filter by date range
        transactions = self._mock_transactions.get(account_id, [])
        return [
            tx for tx in transactions
            if start_date <= tx.date <= end_date
        ]
    
    def disconnect(self, token_info: TokenInfo | None = None) -> bool:
        """Disconnect mock connector"""
        self._logger.info("Disconnecting mock connector")
        self._mock_accounts = []
        self._mock_transactions = {}
        self._connected = False
        return True
    
    def _generate_mock_accounts(self) -> None:
        """Generate mock account data"""
        account_types = ["checking", "savings", "credit"]
        currencies = ["USD", "EUR", "GBP"]
        
        self._mock_accounts = [
            Account(
                account_id=f"mock_acc_{i+1}",
                account_name=f"Mock Account {i+1}",
                account_type=account_types[i % len(account_types)],
                currency=currencies[i % len(currencies)],
                balance=Decimal(random.randint(100, 50000)),
                available_balance=Decimal(random.randint(100, 50000)),
                mask=f"{random.randint(1000, 9999)}",
                institution_name=self.institution_name,
                institution_id=self.institution_id,
                metadata={"mock": True},
            )
            for i in range(self.DEFAULT_ACCOUNT_COUNT)
        ]
    
    def _generate_mock_transactions(self, account_id: str) -> None:
        """Generate mock transaction data"""
        merchants = [
            "Amazon", "Walmart", "Target", "Starbucks", "Uber",
            "Netflix", "Spotify", "Apple Store", "Gas Station", "Grocery Store",
            "Restaurant", "Pharmacy", "Online Purchase", "Utility Bill", "ATM"
        ]
        
        categories = [
            "Shopping", "Food & Drink", "Transportation", "Entertainment",
            "Bills & Utilities", "Health", "Travel", "Income", "Transfer"
        ]
        
        transactions = []
        base_date = date.today()
        
        for i in range(self.DEFAULT_TRANSACTION_COUNT):
            # Random date within last 30 days
            days_ago = random.randint(0, 30)
            tx_date = base_date - timedelta(days=days_ago)
            
            # Random amount between -500 and 200 (negative = debit, positive = credit)
            amount = Decimal(random.randint(-50000, 20000)) / 100
            
            # Determine transaction type
            tx_type = "credit" if amount > 0 else "debit"
            
            merchant = random.choice(merchants)
            category = random.choice(categories)
            
            transactions.append(
                Transaction(
                    transaction_id=f"mock_tx_{account_id}_{i+1}",
                    account_id=account_id,
                    amount=abs(amount),
                    currency="USD",
                    date=tx_date,
                    description=f"{merchant} - Purchase",
                    merchant_name=merchant,
                    category=category,
                    pending=random.random() < 0.1,  # 10% pending
                    transaction_type=tx_type,
                    metadata={"mock": True},
                )
            )
        
        # Sort by date descending
        transactions.sort(key=lambda x: x.date, reverse=True)
        self._mock_transactions[account_id] = transactions
    
    def set_mock_accounts(self, accounts: list[Account]) -> None:
        """Set custom mock accounts (for testing)"""
        self._mock_accounts = accounts
    
    def set_mock_transactions(self, account_id: str, transactions: list[Transaction]) -> None:
        """Set custom mock transactions (for testing)"""
        self._mock_transactions[account_id] = transactions
