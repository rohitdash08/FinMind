"""Tests for Bank Sync functionality."""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.services.bank_connector import (
    BankAccount,
    BankConnector,
    BankConnectionStatus,
    BankTransaction,
    ConnectorRegistry,
    SyncResult,
)
from app.services.bank_connectors.mock import MockBankConnector
from app.services.bank_sync import BankSyncService


class TestBankConnectorInterface:
    """Test the bank connector interface."""
    
    def test_bank_account_dataclass(self):
        """Test BankAccount dataclass creation."""
        account = BankAccount(
            id="acc_123",
            name="Test Account",
            account_type="CHECKING",
            currency="USD",
            balance=Decimal("1000.00"),
        )
        assert account.id == "acc_123"
        assert account.name == "Test Account"
        assert account.balance == Decimal("1000.00")
    
    def test_bank_transaction_dataclass(self):
        """Test BankTransaction dataclass creation."""
        tx = BankTransaction(
            id="tx_123",
            account_id="acc_123",
            date=date.today(),
            amount=Decimal("-50.00"),
            description="Test purchase",
            currency="USD",
        )
        assert tx.id == "tx_123"
        assert tx.amount == Decimal("-50.00")
        assert tx.description == "Test purchase"
    
    def test_sync_result_dataclass(self):
        """Test SyncResult dataclass creation."""
        result = SyncResult(success=True, accounts_synced=2)
        assert result.success is True
        assert result.accounts_synced == 2
        assert result.transactions_synced == 0


class TestMockBankConnector:
    """Test the MockBankConnector implementation."""
    
    @pytest.fixture
    def connector(self):
        """Create a mock connector for testing."""
        config = {"seed": 12345, "account_count": 3, "transaction_count": 10}
        return MockBankConnector("mock", "Mock Bank", config)
    
    def test_mock_connector_authenticate_success(self, connector):
        """Test successful authentication."""
        result = connector.authenticate({"api_key": "test_key"})
        assert result is True
        assert connector.is_authenticated() is True
        assert connector.get_connection_status() == BankConnectionStatus.ACTIVE
    
    def test_mock_connector_authenticate_failure(self, connector):
        """Test failed authentication."""
        result = connector.authenticate({"api_key": ""})
        assert result is False
        assert connector.is_authenticated() is False
    
    def test_mock_connector_fetch_accounts(self, connector):
        """Test fetching accounts."""
        connector.authenticate({"api_key": "test"})
        accounts = connector.fetch_accounts()
        
        assert len(accounts) == 3
        for account in accounts:
            assert isinstance(account, BankAccount)
            assert account.id.startswith("mock_acc_")
            assert account.institution_name == "Mock Bank"
    
    def test_mock_connector_fetch_accounts_unauthenticated(self, connector):
        """Test fetching accounts without authentication."""
        with pytest.raises(ValueError, match="Not authenticated"):
            connector.fetch_accounts()
    
    def test_mock_connector_fetch_transactions(self, connector):
        """Test fetching transactions."""
        connector.authenticate({"api_key": "test"})
        accounts = connector.fetch_accounts()
        
        transactions = connector.fetch_transactions(accounts[0].id)
        
        assert len(transactions) == 10
        for tx in transactions:
            assert isinstance(tx, BankTransaction)
            assert tx.account_id == accounts[0].id
    
    def test_mock_connector_fetch_transactions_date_filter(self, connector):
        """Test fetching transactions with date filter."""
        connector.authenticate({"api_key": "test"})
        accounts = connector.fetch_accounts()
        
        start_date = date.today() - timedelta(days=30)
        end_date = date.today()
        
        transactions = connector.fetch_transactions(
            accounts[0].id,
            start_date=start_date,
            end_date=end_date
        )
        
        assert len(transactions) > 0
        for tx in transactions:
            assert start_date <= tx.date <= end_date
    
    def test_mock_connector_refresh(self, connector):
        """Test connection refresh."""
        connector.authenticate({"api_key": "test"})
        result = connector.refresh()
        assert result is True
    
    def test_mock_connector_disconnect(self, connector):
        """Test disconnection."""
        connector.authenticate({"api_key": "test"})
        result = connector.disconnect()
        
        assert result is True
        assert connector.is_authenticated() is False
        assert connector.get_connection_status() == BankConnectionStatus.DISCONNECTED
    
    def test_mock_connector_health_check(self, connector):
        """Test health check."""
        connector.authenticate({"api_key": "test"})
        health = connector.health_check()
        
        assert health["status"] == "healthy"
        assert "latency_ms" in health
        assert "api_version" in health


class TestConnectorRegistry:
    """Test the ConnectorRegistry."""
    
    def test_register_connector(self):
        """Test registering a connector."""
        ConnectorRegistry.register("test_mock", MockBankConnector)
        
        connector_class = ConnectorRegistry.get("test_mock")
        assert connector_class == MockBankConnector
    
    def test_create_connector(self):
        """Test creating a connector instance."""
        ConnectorRegistry.register("test_mock", MockBankConnector)
        
        connector = ConnectorRegistry.create_connector("test_mock", {"name": "Test"})
        
        assert isinstance(connector, MockBankConnector)
        assert connector.name == "Test"
    
    def test_list_connectors(self):
        """Test listing registered connectors."""
        connectors = ConnectorRegistry.list_connectors()
        
        assert "mock" in connectors
        assert connectors["mock"] == MockBankConnector


class TestBankSyncService:
    """Test the BankSyncService."""
    
    @pytest.fixture
    def service(self):
        """Create a bank sync service."""
        return BankSyncService()
    
    @pytest.fixture
    def connected_connector(self):
        """Create an authenticated connector."""
        config = {"seed": 12345, "account_count": 2, "transaction_count": 5}
        connector = MockBankConnector("mock", "Mock Bank", config)
        connector.authenticate({"api_key": "test"})
        return connector
    
    def test_connect_bank_success(self, service):
        """Test successful bank connection."""
        connector = service.connect_bank(
            "mock",
            {"api_key": "test"},
            {"account_count": 2}
        )
        
        assert connector is not None
        assert connector.is_authenticated() is True
    
    def test_connect_bank_failure(self, service):
        """Test failed bank connection."""
        connector = service.connect_bank("mock", {"api_key": ""})
        
        assert connector is None
    
    def test_connect_bank_unknown_connector(self, service):
        """Test connection with unknown connector."""
        connector = service.connect_bank(
            "unknown_connector",
            {"api_key": "test"}
        )
        
        assert connector is None
    
    def test_sync_accounts(self, service, connected_connector):
        """Test syncing accounts."""
        result = service.sync_accounts(user_id=1, connector=connected_connector)
        
        assert result.success is True
        assert result.accounts_synced == 2
    
    def test_sync_accounts_unauthenticated(self, service):
        """Test syncing accounts without authentication."""
        config = {"account_count": 2}
        connector = MockBankConnector("mock", "Mock Bank", config)
        # Don't authenticate
        
        result = service.sync_accounts(user_id=1, connector=connector)
        
        assert result.success is False
        assert "Not authenticated" in result.errors
    
    def test_list_available_connectors(self, service):
        """Test listing available connectors."""
        connectors = service.list_available_connectors()
        
        assert "mock" in connectors
    
    def test_get_connector_status(self, service, connected_connector):
        """Test getting connector status."""
        status = service.get_connector_status(connected_connector)
        
        assert status["connector_id"] == "mock"
        assert status["authenticated"] is True
        assert status["connection_status"] == "ACTIVE"


class TestBankTransactionImport:
    """Test importing bank transactions as expenses."""
    
    def test_import_transactions_to_expenses(self, app, db_session):
        """Test importing transactions creates expenses."""
        from app.models import User, Expense
        from app.services.bank_sync import BankSyncService
        
        # Create a test user
        user = User(
            email="test@example.com",
            password_hash="hashed",
            preferred_currency="USD"
        )
        db_session.add(user)
        db_session.commit()
        
        # Create test transactions
        transactions = [
            BankTransaction(
                id="tx_1",
                account_id="acc_1",
                date=date.today(),
                amount=Decimal("-50.00"),
                description="Coffee Shop",
                currency="USD",
            ),
            BankTransaction(
                id="tx_2",
                account_id="acc_1",
                date=date.today(),
                amount=Decimal("-100.00"),
                description="Grocery Store",
                currency="USD",
            ),
        ]
        
        service = BankSyncService()
        imported = service._import_transactions_to_expenses(user.id, transactions)
        
        assert imported == 2
        
        # Verify expenses were created
        expenses = Expense.query.filter_by(user_id=user.id).all()
        assert len(expenses) == 2
        
        descriptions = [e.notes for e in expenses]
        assert "Coffee Shop" in descriptions
        assert "Grocery Store" in descriptions
    
    def test_import_transactions_skips_duplicates(self, app, db_session):
        """Test that duplicate transactions are skipped."""
        from app.models import User, Expense
        from app.services.bank_sync import BankSyncService
        
        # Create a test user
        user = User(
            email="test2@example.com",
            password_hash="hashed",
            preferred_currency="USD"
        )
        db_session.add(user)
        db_session.commit()
        
        today = date.today()
        
        # Create an existing expense
        existing = Expense(
            user_id=user.id,
            amount=Decimal("50.00"),
            currency="USD",
            notes="Coffee Shop",
            spent_at=today,
        )
        db_session.add(existing)
        db_session.commit()
        
        # Try to import the same transaction
        transactions = [
            BankTransaction(
                id="tx_1",
                account_id="acc_1",
                date=today,
                amount=Decimal("-50.00"),
                description="Coffee Shop",
                currency="USD",
            ),
        ]
        
        service = BankSyncService()
        imported = service._import_transactions_to_expenses(user.id, transactions)
        
        assert imported == 0  # Should skip duplicate
