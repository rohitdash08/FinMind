"""Tests for Bank Sync functionality."""

import pytest
from datetime import datetime, timedelta
from app.connectors.base import (
    BankConnector,
    ConnectionCredentials,
    BankAccount,
    Transaction,
    ConnectionStatus,
    AuthenticationError,
)
from app.connectors.mock import MockBankConnector
from app.connectors import list_connectors, get_connector


class TestConnectorInterface:
    """Test that the base interface is properly defined."""
    
    def test_abstract_methods_exist(self):
        """All required abstract methods should be defined."""
        abstract_methods = [
            'connect',
            'validate_credentials',
            'refresh_connection',
            'get_accounts',
            'get_transactions',
            'get_balance',
            'disconnect',
            'get_connection_status',
        ]
        
        for method in abstract_methods:
            assert hasattr(BankConnector, method)
            assert getattr(BankConnector, method).__isabstractmethod__


class TestMockConnector:
    """Test the mock connector implementation."""
    
    @pytest.fixture
    def connector(self):
        """Create a fresh mock connector."""
        return MockBankConnector()
    
    def test_connector_metadata(self, connector):
        """Connector should have proper metadata."""
        assert connector.name == "mock_bank"
        assert connector.display_name == "MockBank (Test)"
        assert "US" in connector.supported_countries
    
    def test_connect_success(self, connector):
        """Should connect with valid credentials."""
        creds = ConnectionCredentials(
            additional_data={"username": "test", "password": "secret"}
        )
        result = connector.connect(creds)
        
        assert "connection_id" in result
        assert result["status"] == "connected"
        assert "access_token" in result
    
    def test_connect_failure(self, connector):
        """Should fail with invalid credentials."""
        creds = ConnectionCredentials(
            additional_data={"username": "test", "password": "wrong_password"}
        )
        
        with pytest.raises(AuthenticationError):
            connector.connect(creds)
    
    def test_get_accounts(self, connector):
        """Should return accounts after connection."""
        creds = ConnectionCredentials(
            additional_data={"username": "test", "password": "secret"}
        )
        result = connector.connect(creds)
        creds.access_token = result["access_token"]
        
        accounts = connector.get_accounts(creds)
        
        assert len(accounts) == 3
        assert all(isinstance(acc, BankAccount) for acc in accounts)
    
    def test_get_transactions(self, connector):
        """Should return transactions for an account."""
        creds = ConnectionCredentials(
            additional_data={"username": "test", "password": "secret"}
        )
        result = connector.connect(creds)
        creds.access_token = result["access_token"]
        
        accounts = connector.get_accounts(creds)
        start = datetime.utcnow() - timedelta(days=30)
        end = datetime.utcnow()
        
        transactions = connector.get_transactions(
            creds, accounts[0].id, start, end
        )
        
        assert len(transactions) > 0
        assert all(isinstance(txn, Transaction) for txn in transactions)
    
    def test_refresh_connection(self, connector):
        """Should refresh credentials."""
        creds = ConnectionCredentials(
            additional_data={"username": "test", "password": "secret"},
            access_token="old_token"
        )
        
        new_creds = connector.refresh_connection(creds)
        
        assert new_creds.access_token != "old_token"
        assert new_creds.expires_at is not None
    
    def test_disconnect(self, connector):
        """Should disconnect successfully."""
        creds = ConnectionCredentials(
            additional_data={"username": "test", "password": "secret"}
        )
        result = connector.connect(creds)
        creds.access_token = result["access_token"]
        
        result = connector.disconnect(creds)
        
        assert result is True
    
    def test_validate_credentials(self, connector):
        """Should validate credentials."""
        valid_creds = ConnectionCredentials(access_token="valid_token")
        invalid_creds = ConnectionCredentials()
        
        assert connector.validate_credentials(valid_creds) is True
        assert connector.validate_credentials(invalid_creds) is False


class TestConnectorRegistry:
    """Test the connector registry."""
    
    def test_list_connectors(self):
        """Should list available connectors."""
        connectors = list_connectors()
        
        assert len(connectors) >= 1
        assert any(c["id"] == "mock_bank" for c in connectors)
    
    def test_get_connector(self):
        """Should get connector by name."""
        connector = get_connector("mock_bank")
        
        assert connector is not None
        assert connector.name == "mock_bank"
    
    def test_get_unknown_connector(self):
        """Should return None for unknown connector."""
        connector = get_connector("unknown_bank")
        
        assert connector is None


class TestDataClasses:
    """Test data class functionality."""
    
    def test_bank_account_creation(self):
        """Should create BankAccount."""
        account = BankAccount(
            id="acc_123",
            name="Test Account",
            account_type="checking",
            currency="USD",
            balance=1000.00
        )
        
        assert account.id == "acc_123"
        assert account.balance == 1000.00
    
    def test_transaction_creation(self):
        """Should create Transaction."""
        txn = Transaction(
            id="txn_456",
            account_id="acc_123",
            amount=-50.00,
            currency="USD",
            description="Test Purchase",
            transaction_date=datetime.utcnow()
        )
        
        assert txn.amount == -50.00
        assert txn.description == "Test Purchase"
    
    def test_connection_credentials(self):
        """Should create ConnectionCredentials."""
        creds = ConnectionCredentials(
            access_token="token123",
            additional_data={"username": "test"}
        )
        
        assert creds.access_token == "token123"
        assert creds.additional_data["username"] == "test"


class TestPlaidConnector:
    """Test Plaid connector availability."""
    
    def test_plaid_import(self):
        """Should be able to import PlaidConnector."""
        try:
            from app.connectors.plaid import PlaidConnector
            assert True
        except ImportError:
            pytest.skip("Plaid SDK not installed")
    
    def test_plaid_metadata(self):
        """Should have correct metadata."""
        try:
            from app.connectors.plaid import PlaidConnector
            connector = PlaidConnector()
            assert connector.name == "plaid"
            assert "Plaid" in connector.display_name
            assert "transactions" in connector.features
        except ImportError:
            pytest.skip("Plaid SDK not installed")


class TestBankSyncIntegration:
    """Integration tests for full flow."""
    
    @pytest.fixture
    def connector(self):
        return MockBankConnector()
    
    def test_full_sync_flow(self, connector):
        """Test complete sync workflow."""
        # 1. Connect
        creds = ConnectionCredentials(
            additional_data={"username": "test", "password": "secret"}
        )
        result = connector.connect(creds)
        creds.access_token = result["access_token"]
        
        # 2. Get accounts
        accounts = connector.get_accounts(creds)
        assert len(accounts) > 0
        
        # 3. Get transactions
        start = datetime.utcnow() - timedelta(days=30)
        end = datetime.utcnow()
        transactions = connector.get_transactions(creds, accounts[0].id, start, end)
        assert len(transactions) > 0
        
        # 4. Refresh connection
        creds = connector.refresh_connection(creds)
        
        # 5. Disconnect
        result = connector.disconnect(creds)
        assert result is True
    
    def test_date_range_filtering(self, connector):
        """Test that date ranges filter transactions."""
        creds = ConnectionCredentials(
            additional_data={"username": "test", "password": "secret"}
        )
        result = connector.connect(creds)
        creds.access_token = result["access_token"]
        
        accounts = connector.get_accounts(creds)
        
        # Get all transactions
        all_txns = connector.get_transactions(
            creds, accounts[0].id, None, None
        )
        
        # Get recent transactions only
        start = datetime.utcnow() - timedelta(days=7)
        recent_txns = connector.get_transactions(
            creds, accounts[0].id, start, None
        )
        
        assert len(recent_txns) <= len(all_txns)
