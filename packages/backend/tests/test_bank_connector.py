"""
Tests for bank connector service.
"""

import pytest
from datetime import datetime
from app.services.bank_connector import (
    BaseBankConnector,
    MockBankConnector,
    get_connector,
    register_connector,
    CONNECTOR_REGISTRY,
    BankAccount,
    BankTransaction,
    ConnectionStatus,
)


class TestMockBankConnector:
    """Tests for MockBankConnector."""
    
    def test_connector_initialization(self):
        """Test connector can be initialized with config."""
        config = {"mock_accounts": []}
        connector = MockBankConnector(config)
        assert connector.status == ConnectionStatus.DISCONNECTED
    
    def test_connect(self):
        """Test connecting to mock bank."""
        connector = MockBankConnector({})
        result = connector.connect()
        assert result is True
        assert connector.status == ConnectionStatus.CONNECTED
    
    def test_disconnect(self):
        """Test disconnecting from mock bank."""
        connector = MockBankConnector({})
        connector.connect()
        result = connector.disconnect()
        assert result is True
        assert connector.status == ConnectionStatus.DISCONNECTED
    
    def test_get_accounts(self):
        """Test getting accounts from mock bank."""
        connector = MockBankConnector({})
        connector.connect()
        accounts = connector.get_accounts()
        
        assert len(accounts) == 2
        assert all(isinstance(a, BankAccount) for a in accounts)
        assert accounts[0].account_type == "checking"
        assert accounts[1].account_type == "savings"
    
    def test_get_transactions(self):
        """Test getting transactions from mock bank."""
        connector = MockBankConnector({})
        connector.connect()
        transactions = connector.get_transactions("CHK001")
        
        assert len(transactions) == 4
        assert all(isinstance(t, BankTransaction) for t in transactions)
        
        # Check transaction properties
        assert transactions[0].amount == -125.50  # expense
        assert transactions[1].amount == 3500.00  # income
    
    def test_get_transactions_with_date_filter(self):
        """Test filtering transactions by date range."""
        connector = MockBankConnector({})
        connector.connect()
        
        start = datetime(2026, 3, 3)
        end = datetime(2026, 3, 4)
        
        transactions = connector.get_transactions(
            "CHK001", 
            start_date=start, 
            end_date=end
        )
        
        # Should only get transactions within range
        assert len(transactions) == 2
    
    def test_refresh(self):
        """Test refreshing connection."""
        connector = MockBankConnector({})
        connector.connect()
        result = connector.refresh()
        assert result is True


class TestConnectorRegistry:
    """Tests for connector registry."""
    
    def test_get_connector_mock(self):
        """Test getting mock connector from registry."""
        connector = get_connector("mock", {})
        assert isinstance(connector, MockBankConnector)
    
    def test_get_connector_unknown_type(self):
        """Test getting unknown connector type raises error."""
        with pytest.raises(ValueError) as exc_info:
            get_connector("unknown_type", {})
        
        assert "Unknown connector type" in str(exc_info.value)
        assert "mock" in str(exc_info.value)
    
    def test_register_connector(self):
        """Test registering a new connector type."""
        class CustomConnector(MockBankConnector):
            pass
        
        register_connector("custom", CustomConnector)
        
        assert "custom" in CONNECTOR_REGISTRY
        connector = get_connector("custom", {})
        assert isinstance(connector, CustomConnector)


class TestBankAccount:
    """Tests for BankAccount dataclass."""
    
    def test_account_creation(self):
        """Test creating a BankAccount."""
        account = BankAccount(
            account_id="TEST001",
            account_name="Test Account",
            account_type="checking",
            balance=1000.00,
            currency="USD",
            institution_name="Test Bank",
            last_updated=datetime.utcnow()
        )
        
        assert account.account_id == "TEST001"
        assert account.balance == 1000.00


class TestBankTransaction:
    """Tests for BankTransaction dataclass."""
    
    def test_transaction_creation(self):
        """Test creating a BankTransaction."""
        txn = BankTransaction(
            external_id="TXN001",
            date=datetime(2026, 3, 1),
            description="Test Transaction",
            amount=-50.00,
            currency="USD"
        )
        
        assert txn.external_id == "TXN001"
        assert txn.amount == -50.00
        assert txn.pending is False
        assert txn.metadata == {}
    
    def test_transaction_with_metadata(self):
        """Test creating transaction with metadata."""
        txn = BankTransaction(
            external_id="TXN001",
            date=datetime(2026, 3, 1),
            description="Test",
            amount=-50.00,
            currency="USD",
            metadata={"source": "bank_api"}
        )
        
        assert txn.metadata["source"] == "bank_api"
