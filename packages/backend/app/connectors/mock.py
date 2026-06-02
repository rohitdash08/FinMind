"""Mock Bank Connector for testing."""

import uuid
import random
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

try:
    from .base import (
        BankConnector,
        ConnectionCredentials,
        BankAccount,
        Transaction,
        ConnectionStatus,
        AuthenticationError,
    )
except ImportError:
    from base import (
        BankConnector,
        ConnectionCredentials,
        BankAccount,
        Transaction,
        ConnectionStatus,
        AuthenticationError,
    )


class MockBankConnector(BankConnector):
    """Mock bank connector for testing and development."""
    
    name = "mock_bank"
    display_name = "MockBank (Test)"
    description = "A mock bank connector for testing."
    supported_countries = ["US", "CA", "GB", "AU"]
    features = ["transactions", "balance", "oauth", "refresh"]
    
    _connections: Dict[str, Dict] = {}
    _accounts: Dict[str, List[Dict]] = {}
    _transactions: Dict[str, List[Dict]] = {}
    
    MERCHANTS = {
        "grocery": ["Whole Foods", "Trader Joe's", "Safeway"],
        "restaurant": ["Chipotle", "Starbucks", "McDonald's"],
        "shopping": ["Amazon", "Target", "Walmart"],
    }
    
    def connect(self, credentials: ConnectionCredentials) -> Dict[str, Any]:
        """Establish a mock connection."""
        if not credentials.additional_data:
            raise AuthenticationError("No credentials provided")
        
        username = credentials.additional_data.get("username")
        password = credentials.additional_data.get("password")
        
        if not username or not password:
            raise AuthenticationError("Username and password required")
        
        if password == "wrong_password":
            raise AuthenticationError("Invalid credentials")
        
        connection_id = str(uuid.uuid4())
        access_token = f"mock_token_{uuid.uuid4().hex[:16]}"
        expires_at = datetime.utcnow() + timedelta(days=30)
        
        self._connections[connection_id] = {
            "id": connection_id,
            "username": username,
            "status": ConnectionStatus.CONNECTED,
            "created_at": datetime.utcnow(),
        }
        
        # Generate mock accounts
        self._generate_accounts(connection_id)
        
        return {
            "connection_id": connection_id,
            "status": ConnectionStatus.CONNECTED.value,
            "access_token": access_token,
            "expires_at": expires_at,
            "institution_name": "MockBank"
        }
    
    def _generate_accounts(self, connection_id: str) -> None:
        """Generate mock accounts."""
        accounts = []
        account_types = [
            ("checking", "Primary Checking", 2500.00),
            ("savings", "Savings", 15000.00),
            ("credit", "Credit Card", -450.00)
        ]
        
        for acc_type, name, balance in account_types:
            account_id = f"mock_acc_{uuid.uuid4().hex[:8]}"
            accounts.append({
                "id": account_id,
                "name": name,
                "type": acc_type,
                "balance": balance,
                "currency": "USD",
                "masked_number": f"****{random.randint(1000, 9999)}",
            })
            self._generate_transactions(account_id)
        
        self._accounts[connection_id] = accounts
    
    def _generate_transactions(self, account_id: str) -> None:
        """Generate mock transactions."""
        transactions = []
        base_date = datetime.utcnow() - timedelta(days=30)
        
        for i in range(20):
            txn_date = base_date + timedelta(days=i)
            category = random.choice(list(self.MERCHANTS.keys()))
            merchant = random.choice(self.MERCHANTS[category])
            amount = round(random.uniform(10, 200), 2)
            
            transactions.append({
                "id": f"mock_txn_{uuid.uuid4().hex[:12]}",
                "account_id": account_id,
                "amount": -amount,
                "currency": "USD",
                "description": f"{merchant} Purchase",
                "transaction_date": txn_date,
                "merchant_name": merchant,
                "transaction_type": "debit",
            })
        
        self._transactions[account_id] = transactions
    
    def validate_credentials(self, credentials: ConnectionCredentials) -> bool:
        """Check if credentials are valid."""
        if not credentials.access_token:
            return False
        return True
    
    def refresh_connection(self, credentials: ConnectionCredentials) -> ConnectionCredentials:
        """Refresh mock credentials."""
        if not credentials.access_token:
            raise AuthenticationError("No token to refresh")
        
        return ConnectionCredentials(
            access_token=f"mock_token_{uuid.uuid4().hex[:16]}",
            refresh_token=credentials.refresh_token,
            expires_at=datetime.utcnow() + timedelta(days=30),
            additional_data=credentials.additional_data
        )
    
    def get_accounts(self, credentials: ConnectionCredentials) -> List[BankAccount]:
        """Get all mock accounts."""
        if not self.validate_credentials(credentials):
            raise AuthenticationError("Invalid credentials")
        
        connection_id = self._get_connection_id(credentials.access_token)
        accounts_data = self._accounts.get(connection_id, [])
        
        return [
            BankAccount(
                id=a["id"],
                name=a["name"],
                account_type=a["type"],
                currency=a["currency"],
                balance=a["balance"],
                masked_number=a.get("masked_number"),
                institution_name="MockBank"
            )
            for a in accounts_data
        ]
    
    def get_transactions(
        self,
        credentials: ConnectionCredentials,
        account_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Transaction]:
        """Get transactions for an account."""
        if not self.validate_credentials(credentials):
            raise AuthenticationError("Invalid credentials")
        
        transactions_data = self._transactions.get(account_id, [])
        transactions = []
        
        for t in transactions_data:
            txn_date = t["transaction_date"]
            if start_date and txn_date < start_date:
                continue
            if end_date and txn_date > end_date:
                continue
            
            transactions.append(Transaction(
                id=t["id"],
                account_id=t["account_id"],
                amount=t["amount"],
                currency=t["currency"],
                description=t["description"],
                transaction_date=txn_date,
                merchant_name=t.get("merchant_name"),
                transaction_type=t["transaction_type"],
            ))
        
        return transactions
    
    def get_balance(self, credentials: ConnectionCredentials, account_id: str) -> BankAccount:
        """Get account balance."""
        accounts = self.get_accounts(credentials)
        for account in accounts:
            if account.id == account_id:
                return account
        raise AccountNotFoundError(f"Account {account_id} not found")
    
    def disconnect(self, credentials: ConnectionCredentials) -> bool:
        """Disconnect from mock bank."""
        connection_id = self._get_connection_id(credentials.access_token)
        if connection_id in self._connections:
            self._connections[connection_id]["status"] = ConnectionStatus.DISCONNECTED
            return True
        return False
    
    def get_connection_status(self, credentials: ConnectionCredentials) -> ConnectionStatus:
        """Get connection status."""
        connection_id = self._get_connection_id(credentials.access_token)
        conn = self._connections.get(connection_id, {})
        return conn.get("status", ConnectionStatus.ERROR)
    
    def _get_connection_id(self, access_token: str) -> str:
        """Extract connection ID from token."""
        # In real implementation, would decode JWT
        for conn_id, conn in self._connections.items():
            if conn.get("token") == access_token:
                return conn_id
        # Return first connection for mock purposes
        if self._connections:
            return list(self._connections.keys())[0]
        return str(uuid.uuid4())
