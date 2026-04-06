"""Tests for the bank connector architecture."""
import pytest
from datetime import date, timedelta

from app.connectors import (
    BaseConnector,
    ConnectorType,
    ConnectorRegistry,
    Transaction,
    Account,
)
from app.connectors.mock import MockConnector


class TestConnectorType:
    """Tests for the ConnectorType enum."""

    def test_connector_type_values(self):
        """Test that ConnectorType has expected values."""
        assert ConnectorType.MOCK.value == "mock"

    def test_connector_type_is_string_enum(self):
        """Test that ConnectorType is a string enum."""
        assert isinstance(ConnectorType.MOCK, str)


class TestTransaction:
    """Tests for the Transaction dataclass."""

    def test_transaction_creation(self):
        """Test creating a Transaction object."""
        tx = Transaction(
            date=date(2024, 1, 15),
            amount=100.50,
            description="Test transaction",
            category_id=None,
            expense_type="EXPENSE",
            currency="USD",
        )
        assert tx.date == date(2024, 1, 15)
        assert tx.amount == 100.50
        assert tx.description == "Test transaction"
        assert tx.category_id is None
        assert tx.expense_type == "EXPENSE"
        assert tx.currency == "USD"

    def test_transaction_with_income(self):
        """Test creating an income transaction."""
        tx = Transaction(
            date=date(2024, 1, 15),
            amount=5000.00,
            description="Salary",
            expense_type="INCOME",
        )
        assert tx.expense_type == "INCOME"


class TestAccount:
    """Tests for the Account dataclass."""

    def test_account_creation(self):
        """Test creating an Account object."""
        account = Account(
            account_id="test_001",
            account_name="Test Checking",
            account_type="CHECKING",
            balance=1000.00,
            currency="USD",
        )
        assert account.account_id == "test_001"
        assert account.account_name == "Test Checking"
        assert account.account_type == "CHECKING"
        assert account.balance == 1000.00
        assert account.currency == "USD"


class TestMockConnector:
    """Tests for the MockConnector implementation."""

    def test_connector_type(self):
        """Test that MockConnector returns correct type."""
        connector = MockConnector()
        assert connector.connector_type == ConnectorType.MOCK

    def test_validate_credentials(self):
        """Test that mock credentials are always valid."""
        connector = MockConnector()
        assert connector.validate_credentials() is True

    def test_get_accounts(self):
        """Test getting accounts from mock connector."""
        connector = MockConnector()
        accounts = connector.get_accounts(user_id=1)
        assert len(accounts) == 3
        assert all(isinstance(a, Account) for a in accounts)
        account_ids = [a.account_id for a in accounts]
        assert "mock_checking_001" in account_ids
        assert "mock_savings_001" in account_ids
        assert "mock_credit_001" in account_ids

    def test_import_transactions_default_dates(self):
        """Test importing transactions with default date range."""
        connector = MockConnector()
        transactions = connector.import_transactions(user_id=1)
        assert isinstance(transactions, list)
        assert all(isinstance(t, Transaction) for t in transactions)
        # Default is 30 days, should have transactions
        assert len(transactions) > 0

    def test_import_transactions_custom_dates(self):
        """Test importing transactions with custom date range."""
        connector = MockConnector()
        from_date = date(2024, 1, 1)
        to_date = date(2024, 1, 7)
        transactions = connector.import_transactions(
            user_id=1,
            from_date=from_date,
            to_date=to_date,
        )
        assert isinstance(transactions, list)
        # Should have transactions for 7 days
        assert len(transactions) > 0
        # All transactions should be within date range
        for t in transactions:
            assert from_date <= t.date <= to_date

    def test_import_transactions_sorted_by_date(self):
        """Test that transactions are sorted by date descending."""
        connector = MockConnector()
        transactions = connector.import_transactions(
            user_id=1,
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 10),
        )
        dates = [t.date for t in transactions]
        # Should be sorted descending (newest first)
        assert dates == sorted(dates, reverse=True)

    def test_import_transactions_has_expense_and_income(self):
        """Test that transactions include both expenses and income."""
        connector = MockConnector()
        transactions = connector.import_transactions(
            user_id=1,
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 31),
        )
        expense_types = set(t.expense_type for t in transactions)
        assert "EXPENSE" in expense_types
        assert "INCOME" in expense_types

    def test_refresh(self):
        """Test the refresh method."""
        connector = MockConnector()
        result = connector.refresh(user_id=1)
        assert isinstance(result, dict)
        assert result["status"] == "success"
        assert "new_transactions" in result
        assert "accounts" in result
        assert "last_refresh" in result
        assert result["accounts"] == 3


class TestConnectorRegistry:
    """Tests for the ConnectorRegistry."""

    def test_register_connector(self):
        """Test registering a custom connector."""

        class TestConnector(BaseConnector):
            @property
            def connector_type(self) -> ConnectorType:
                return ConnectorType.MOCK

            def import_transactions(
                self,
                user_id: int,
                account_id: str | None = None,
                from_date: date | None = None,
                to_date: date | None = None,
            ) -> list[Transaction]:
                return []

            def refresh(self, user_id: int) -> dict:
                return {"status": "ok"}

            def get_accounts(self, user_id: int) -> list[Account]:
                return []

        # Register the test connector
        ConnectorRegistry.register(ConnectorType.MOCK)(TestConnector)

        # Should be able to get the connector
        connector = ConnectorRegistry.get_connector(ConnectorType.MOCK)
        assert isinstance(connector, TestConnector)

    def test_get_connector_unknown_type(self):
        """Test that getting an unknown connector raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            ConnectorRegistry.get_connector("unknown_type")  # type: ignore
        assert "not registered" in str(exc_info.value)

    def test_list_connectors(self):
        """Test listing available connectors."""
        connectors = ConnectorRegistry.list_connectors()
        assert isinstance(connectors, list)
        assert ConnectorType.MOCK in connectors


class TestBaseConnectorInterface:
    """Tests to verify the BaseConnector interface."""

    def test_mock_connector_implements_interface(self):
        """Test that MockConnector implements all required methods."""
        connector = MockConnector()

        # Check all required properties and methods exist
        assert hasattr(connector, "connector_type")
        assert callable(connector.import_transactions)
        assert callable(connector.refresh)
        assert callable(connector.get_accounts)
        assert callable(connector.validate_credentials)

        # Check return types
        assert isinstance(connector.connector_type, ConnectorType)
        assert isinstance(connector.import_transactions(1), list)
        assert isinstance(connector.refresh(1), dict)
        assert isinstance(connector.get_accounts(1), list)
        assert isinstance(connector.validate_credentials(), bool)
