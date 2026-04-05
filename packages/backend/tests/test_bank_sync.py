"""
Tests for Bank Sync Connector Architecture
"""

import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from app.services.bank_connector import (
    BankConnector,
    BankTransaction,
    BankAccount,
    ConnectorConfig,
    ConnectorRegistry,
    TransactionType,
    register_connector,
)
from app.services.bank_sync import BankSyncService
from app.services.mock_bank_connector import MockBankConnector


class TestBankConnector:
    """Test the BankConnector base class and registry."""

    def test_connector_registry_register(self):
        """Test registering a connector."""
        # Create a test connector
        @register_connector
        class TestConnector(BankConnector):
            @property
            def connector_type(self):
                return "test"
            
            @property
            def display_name(self):
                return "Test Connector"
            
            def connect(self, config):
                return True
            
            def disconnect(self):
                return True
            
            def get_accounts(self):
                return []
            
            def get_transactions(self, account_id, from_date=None, to_date=None):
                return []
            
            def refresh_transactions(self, account_id, since):
                return []
        
        # Check it's registered
        connector = ConnectorRegistry.get_connector("test")
        assert connector is not None
        assert connector.connector_type == "test"
        assert connector.display_name == "Test Connector"

    def test_connector_registry_list(self):
        """Test listing connectors."""
        connectors = ConnectorRegistry.list_connectors()
        assert isinstance(connectors, list)
        # Should have at least the mock connector
        assert any(c["connector_type"] == "mock" for c in connectors)

    def test_connector_registry_clear(self):
        """Test clearing connector instances."""
        ConnectorRegistry.clear_instances()
        # Should still have the class registered
        assert "mock" in ConnectorRegistry._connectors


class TestMockBankConnector:
    """Test the MockBankConnector."""

    def test_mock_connector_properties(self):
        """Test mock connector properties."""
        connector = MockBankConnector()
        assert connector.connector_type == "mock"
        assert connector.display_name == "Mock Bank (Development)"
        assert "import" in connector.supported_features
        assert "refresh" in connector.supported_features

    def test_mock_connect_disconnect(self):
        """Test connecting and disconnecting."""
        connector = MockBankConnector()
        config = ConnectorConfig(
            connector_type="mock",
            user_id=1,
            credentials={"test": "credentials"},
        )
        
        result = connector.connect(config)
        assert result is True
        assert connector.get_connection_status()["connected"] is True
        
        accounts = connector.get_accounts()
        assert len(accounts) > 0
        assert all(isinstance(a, BankAccount) for a in accounts)
        
        result = connector.disconnect()
        assert result is True
        assert connector.get_connection_status()["connected"] is False

    def test_mock_get_transactions(self):
        """Test getting transactions."""
        connector = MockBankConnector()
        config = ConnectorConfig(
            connector_type="mock",
            user_id=1,
            credentials={},
        )
        connector.connect(config)
        
        accounts = connector.get_accounts()
        assert len(accounts) > 0
        
        transactions = connector.get_transactions(accounts[0].account_id)
        assert len(transactions) > 0
        assert all(isinstance(t, BankTransaction) for t in transactions)

    def test_mock_get_transactions_with_date_filter(self):
        """Test getting transactions with date filtering."""
        connector = MockBankConnector()
        config = ConnectorConfig(
            connector_type="mock",
            user_id=1,
            credentials={},
        )
        connector.connect(config)
        
        accounts = connector.get_accounts()
        today = date.today()
        from_date = today.replace(day=1)  # First of month
        
        transactions = connector.get_transactions(
            accounts[0].account_id,
            from_date=from_date,
        )
        
        for tx in transactions:
            assert tx.date >= from_date

    def test_mock_refresh_transactions(self):
        """Test refreshing transactions."""
        connector = MockBankConnector()
        config = ConnectorConfig(
            connector_type="mock",
            user_id=1,
            credentials={},
        )
        connector.connect(config)
        
        accounts = connector.get_accounts()
        since = datetime.now()
        
        new_transactions = connector.refresh_transactions(
            accounts[0].account_id,
            since,
        )
        
        # Should return some new transactions
        assert isinstance(new_transactions, list)


class TestBankTransaction:
    """Test the BankTransaction dataclass."""

    def test_to_expense_dict_expense(self):
        """Test converting expense transaction to expense dict."""
        tx = BankTransaction(
            date=date(2024, 1, 15),
            amount=50.00,
            description="Test Expense",
            transaction_type=TransactionType.EXPENSE,
            currency="USD",
        )
        
        expense_dict = tx.to_expense_dict()
        
        assert expense_dict["date"] == "2024-01-15"
        assert expense_dict["amount"] == 50.00
        assert expense_dict["description"] == "Test Expense"
        assert expense_dict["expense_type"] == "EXPENSE"
        assert expense_dict["currency"] == "USD"

    def test_to_expense_dict_income(self):
        """Test converting income transaction to expense dict."""
        tx = BankTransaction(
            date=date(2024, 1, 15),
            amount=1000.00,
            description="Payroll",
            transaction_type=TransactionType.INCOME,
            currency="USD",
        )
        
        expense_dict = tx.to_expense_dict()
        
        assert expense_dict["expense_type"] == "INCOME"
        assert expense_dict["amount"] == 1000.00


class TestBankSyncService:
    """Test the BankSyncService."""

    def test_list_available_connectors(self):
        """Test listing available connectors."""
        connectors = BankSyncService.list_available_connectors()
        assert isinstance(connectors, list)
        assert len(connectors) > 0
        assert any(c["connector_type"] == "mock" for c in connectors)

    def test_get_connector(self):
        """Test getting a connector."""
        connector = BankSyncService.get_connector("mock")
        assert connector is not None
        assert connector.connector_type == "mock"

    def test_connect_mock(self):
        """Test connecting to mock connector."""
        result = BankSyncService.connect(
            user_id=1,
            connector_type="mock",
            credentials={},
        )
        
        assert result["success"] is True
        assert result["connector_type"] == "mock"
        assert "accounts" in result
        assert len(result["accounts"]) > 0

    def test_connect_invalid_type(self):
        """Test connecting with invalid connector type."""
        result = BankSyncService.connect(
            user_id=1,
            connector_type="nonexistent",
            credentials={},
        )
        
        assert result["success"] is False
        assert "error" in result

    def test_disconnect(self):
        """Test disconnecting."""
        # First connect
        BankSyncService.connect(
            user_id=1,
            connector_type="mock",
            credentials={},
        )
        
        # Then disconnect
        result = BankSyncService.disconnect("mock")
        assert result["success"] is True

    def test_get_connection_status(self):
        """Test getting connection status."""
        # Connect first
        BankSyncService.connect(
            user_id=1,
            connector_type="mock",
            credentials={},
        )
        
        status = BankSyncService.get_connection_status("mock")
        assert status["connected"] is True
        assert status["connector_type"] == "mock"

    def test_import_transactions(self, app_fixture):
        """Test importing transactions."""
        # Connect first
        BankSyncService.connect(
            user_id=1,
            connector_type="mock",
            credentials={},
        )
        
        # Get an account
        accounts = BankSyncService.get_accounts("mock")
        assert len(accounts) > 0
        
        result = BankSyncService.import_transactions(
            user_id=1,
            connector_type="mock",
            account_id=accounts[0]["account_id"],
        )
        
        assert result["success"] is True
        assert result["total"] > 0
        assert "transactions" in result

    def test_import_transactions_with_date_filter(self, app_fixture):
        """Test importing transactions with date filter."""
        BankSyncService.connect(
            user_id=1,
            connector_type="mock",
            credentials={},
        )
        
        accounts = BankSyncService.get_accounts("mock")
        today = date.today()
        
        result = BankSyncService.import_transactions(
            user_id=1,
            connector_type="mock",
            account_id=accounts[0]["account_id"],
            from_date=date(today.year, 1, 1),
            to_date=today,
        )
        
        assert result["success"] is True

    def test_refresh_transactions(self, app_fixture):
        """Test refreshing transactions."""
        BankSyncService.connect(
            user_id=1,
            connector_type="mock",
            credentials={},
        )
        
        accounts = BankSyncService.get_accounts("mock")
        since = datetime.now()
        
        result = BankSyncService.refresh_transactions(
            user_id=1,
            connector_type="mock",
            account_id=accounts[0]["account_id"],
            since=since,
        )
        
        assert result["success"] is True
        assert result["new_count"] >= 0

    def test_commit_transactions(self, app_fixture):
        """Test committing transactions."""
        # Create some test transactions
        transactions = [
            {
                "date": "2024-01-15",
                "amount": 50.00,
                "description": "Test Expense",
                "expense_type": "EXPENSE",
                "currency": "USD",
            },
            {
                "date": "2024-01-16",
                "amount": 100.00,
                "description": "Test Income",
                "expense_type": "INCOME",
                "currency": "USD",
            },
        ]
        
        result = BankSyncService.commit_transactions(
            user_id=1,
            transactions=transactions,
        )
        
        assert result["success"] is True
        assert result["inserted"] == 2
        assert result["duplicates"] == 0

    def test_commit_duplicate_transactions(self, app_fixture):
        """Test committing duplicate transactions."""
        transactions = [
            {
                "date": "2024-01-15",
                "amount": 50.00,
                "description": "Duplicate Test",
                "expense_type": "EXPENSE",
                "currency": "USD",
            },
        ]
        
        # First commit
        result1 = BankSyncService.commit_transactions(
            user_id=1,
            transactions=transactions,
        )
        assert result1["inserted"] == 1
        
        # Second commit (should be duplicate)
        result2 = BankSyncService.commit_transactions(
            user_id=1,
            transactions=transactions,
        )
        assert result2["duplicates"] == 1
        assert result2["inserted"] == 0


class TestBankSyncAPI:
    """Test the Bank Sync API endpoints."""

    def test_list_connectors(self, client, auth_header):
        """Test GET /bank-sync/connectors."""
        r = client.get("/bank-sync/connectors", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert any(c["connector_type"] == "mock" for c in data)

    def test_connect(self, client, auth_header):
        """Test POST /bank-sync/connect."""
        r = client.post(
            "/bank-sync/connect",
            json={"connector_type": "mock", "credentials": {}},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True
        assert "accounts" in data

    def test_connect_missing_type(self, client, auth_header):
        """Test POST /bank-sync/connect without connector_type."""
        r = client.post(
            "/bank-sync/connect",
            json={"credentials": {}},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_disconnect(self, client, auth_header):
        """Test POST /bank-sync/disconnect."""
        # Connect first
        client.post(
            "/bank-sync/connect",
            json={"connector_type": "mock", "credentials": {}},
            headers=auth_header,
        )
        
        # Then disconnect
        r = client.post(
            "/bank-sync/disconnect",
            json={"connector_type": "mock"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["success"] is True

    def test_get_status(self, client, auth_header):
        """Test GET /bank-sync/status."""
        # Connect first
        client.post(
            "/bank-sync/connect",
            json={"connector_type": "mock", "credentials": {}},
            headers=auth_header,
        )
        
        r = client.get(
            "/bank-sync/status?connector_type=mock",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["connected"] is True

    def test_get_accounts(self, client, auth_header):
        """Test GET /bank-sync/accounts."""
        # Connect first
        client.post(
            "/bank-sync/connect",
            json={"connector_type": "mock", "credentials": {}},
            headers=auth_header,
        )
        
        r = client.get(
            "/bank-sync/accounts?connector_type=mock",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_import_transactions(self, client, auth_header):
        """Test POST /bank-sync/import."""
        # Connect first
        client.post(
            "/bank-sync/connect",
            json={"connector_type": "mock", "credentials": {}},
            headers=auth_header,
        )
        
        # Get accounts
        accounts = client.get(
            "/bank-sync/accounts?connector_type=mock",
            headers=auth_header,
        ).get_json()
        
        r = client.post(
            "/bank-sync/import",
            json={
                "connector_type": "mock",
                "account_id": accounts[0]["account_id"],
            },
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True
        assert data["total"] > 0

    def test_import_missing_params(self, client, auth_header):
        """Test POST /bank-sync/import with missing params."""
        r = client.post(
            "/bank-sync/import",
            json={},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_refresh_transactions(self, client, auth_header):
        """Test POST /bank-sync/refresh."""
        # Connect first
        client.post(
            "/bank-sync/connect",
            json={"connector_type": "mock", "credentials": {}},
            headers=auth_header,
        )
        
        accounts = client.get(
            "/bank-sync/accounts?connector_type=mock",
            headers=auth_header,
        ).get_json()
        
        r = client.post(
            "/bank-sync/refresh",
            json={
                "connector_type": "mock",
                "account_id": accounts[0]["account_id"],
                "since": datetime.now().isoformat(),
            },
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True

    def test_commit_transactions(self, client, auth_header):
        """Test POST /bank-sync/commit."""
        transactions = [
            {
                "date": "2024-02-01",
                "amount": 25.00,
                "description": "API Test",
                "expense_type": "EXPENSE",
                "currency": "USD",
            },
        ]
        
        r = client.post(
            "/bank-sync/commit",
            json={"transactions": transactions},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["success"] is True
        assert data["inserted"] == 1

    def test_commit_empty_transactions(self, client, auth_header):
        """Test POST /bank-sync/commit with empty transactions."""
        r = client.post(
            "/bank-sync/commit",
            json={"transactions": []},
            headers=auth_header,
        )
        assert r.status_code == 400


# Import the fixtures
pytest.fixture(autouse=True)
def reset_connector():
    """Reset connector state between tests."""
    yield
    # Clean up after test
    try:
        connector = ConnectorRegistry.get_connector("mock")
        if connector:
            connector.disconnect()
    except Exception:
        pass