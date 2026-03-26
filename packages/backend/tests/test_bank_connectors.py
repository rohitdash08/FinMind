"""
Tests for the pluggable bank connector architecture.
"""
import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.services.bank_connectors import (
    BankConnector,
    ConnectorError,
    ConnectorNotFoundError,
    Transaction,
    TransactionType,
    Account,
    AccountType,
    connector_registry,
    MockBankConnector,
)
from app.services.bank_connectors.registry import ConnectorRegistry
from app.services.bank_connectors.base import (
    AuthenticationError,
    AccountNotFoundError,
    RateLimitError,
    ConnectorAuthStatus,
)


class TestMockBankConnector:
    """Tests for the MockBankConnector."""

    def test_connect_returns_auth_status(self):
        conn = MockBankConnector({"user_id": "user123", "mode": "default"})
        status = conn.get_auth_status()
        assert status.connected is True
        assert status.user_id == "user123"
        assert status.institution_name == "Mock Bank (Dev)"

    def test_list_accounts_returns_accounts(self):
        conn = MockBankConnector({"user_id": "user123", "mode": "default"})
        accounts = conn.list_accounts()
        assert len(accounts) >= 1
        assert all(isinstance(a, Account) for a in accounts)
        assert all(a.account_id for a in accounts)
        assert all(a.institution_name == "Mock Bank (Dev)" for a in accounts)

    def test_list_accounts_empty_mode(self):
        conn = MockBankConnector({"user_id": "user123", "mode": "empty"})
        assert conn.list_accounts() == []

    def test_error_mode_auth_fails(self):
        conn = MockBankConnector({"user_id": "user123", "mode": "error"})
        status = conn.get_auth_status()
        assert status.connected is False
        assert "error" in status.error_message.lower()

    def test_get_transactions_returns_list(self):
        conn = MockBankConnector({"user_id": "user123", "seed": 42, "mode": "default"})
        accounts = conn.list_accounts()
        assert accounts
        txs = conn.get_transactions(accounts[0].account_id)
        assert isinstance(txs, list)
        assert all(isinstance(t, Transaction) for t in txs)
        # Dates should be sorted oldest first
        dates = [t.date for t in txs]
        assert dates == sorted(dates)

    def test_get_transactions_empty_mode(self):
        conn = MockBankConnector({"user_id": "user123", "mode": "empty"})
        # In empty mode, there are no accounts
        assert conn.list_accounts() == []
        # Transactions for any account return empty since no accounts exist
        assert conn.get_transactions("any-account-id") == []

    def test_get_transactions_date_filter(self):
        conn = MockBankConnector({"user_id": "user123", "seed": 42})
        accounts = conn.list_accounts()
        today = date.today()
        last_week = date.today()
        import datetime
        last_week = today - datetime.timedelta(days=7)
        txs = conn.get_transactions(
            accounts[0].account_id,
            from_date=last_week,
            to_date=today,
        )
        for t in txs:
            assert last_week <= t.date <= today

    def test_get_transactions_unknown_account_raises(self):
        conn = MockBankConnector({"user_id": "user123"})
        with pytest.raises(ConnectorError):
            conn.get_transactions("nonexistent-account-id")

    def test_normalize_transactions(self):
        conn = MockBankConnector({"user_id": "user123", "seed": 42})
        accounts = conn.list_accounts()
        txs = conn.get_transactions(accounts[0].account_id)
        rows = conn.normalize_transactions(txs)
        assert isinstance(rows, list)
        if rows:
            row = rows[0]
            assert "date" in row
            assert "amount" in row
            assert "description" in row
            assert "expense_type" in row

    def test_transaction_to_expense_dict(self):
        tx = Transaction(
            date=date(2024, 1, 15),
            amount=42.50,
            description="Test Transaction",
            transaction_type=TransactionType.EXPENSE,
            currency="USD",
        )
        d = tx.to_expense_dict()
        assert d["date"] == "2024-01-15"
        assert d["amount"] == 42.50
        assert d["description"] == "Test Transaction"
        assert d["expense_type"] == "EXPENSE"

    def test_transaction_to_expense_dict_income(self):
        tx = Transaction(
            date=date(2024, 1, 15),
            amount=100.00,
            description="Salary",
            transaction_type=TransactionType.INCOME,
            currency="USD",
        )
        d = tx.to_expense_dict()
        assert d["expense_type"] == "INCOME"

    def test_reproducible_with_seed(self):
        """Seed produces reproducible transactions for the same connector config."""
        conn1 = MockBankConnector({"user_id": "user1", "seed": 9999})
        conn2 = MockBankConnector({"user_id": "user1", "seed": 9999})
        a1 = conn1.list_accounts()
        a2 = conn2.list_accounts()
        # Same user + same seed → identical account IDs
        assert a1[0].account_id == a2[0].account_id
        # Transactions are reproducible with same seed
        txs1 = conn1.get_transactions(a1[0].account_id)
        txs2 = conn2.get_transactions(a2[0].account_id)
        assert len(txs1) == len(txs2)
        assert [t.transaction_id for t in txs1] == [t.transaction_id for t in txs2]


class TestConnectorRegistry:
    """Tests for the ConnectorRegistry."""

    def test_register_and_create(self):
        registry = ConnectorRegistry()
        registry.register("test", MockBankConnector)
        conn = registry.create("test", {"user_id": "123"})
        assert isinstance(conn, MockBankConnector)
        assert conn.user_id == "123"

    def test_register_duplicate_raises(self):
        registry = ConnectorRegistry()
        registry.register("test", MockBankConnector)
        with pytest.raises(ValueError, match="already registered"):
            registry.register("test", MockBankConnector)

    def test_force_register_replaces(self):
        registry = ConnectorRegistry()
        registry.register("test", MockBankConnector)
        registry.force_register("test", MockBankConnector)  # Should not raise

    def test_create_unknown_raises(self):
        registry = ConnectorRegistry()
        with pytest.raises(ConnectorNotFoundError):
            registry.create("nonexistent", {})

    def test_list_connectors(self):
        registry = ConnectorRegistry()
        registry.register("mock", MockBankConnector)
        connectors = registry.list_connectors()
        assert any(c["name"] == "mock" for c in connectors)
        mock_conn = next(c for c in connectors if c["name"] == "mock")
        assert mock_conn["display_name"] == "Mock Bank (Dev)"
        assert mock_conn["supports_refresh"] is True

    def test_is_registered(self):
        registry = ConnectorRegistry()
        registry.register("mock", MockBankConnector)
        assert registry.is_registered("mock") is True
        assert registry.is_registered("chase") is False

    def test_get_returns_factory(self):
        registry = ConnectorRegistry()
        registry.register("mock", MockBankConnector)
        factory = registry.get("mock")
        assert callable(factory)


class TestAutoRegisteredMockConnector:
    """Verify that the global registry auto-registers the mock connector."""

    def test_mock_is_registered(self):
        assert connector_registry.is_registered("mock") is True

    def test_mock_can_be_created_from_global_registry(self):
        conn = connector_registry.create("mock", {"user_id": "test-user"})
        assert isinstance(conn, MockBankConnector)
        assert conn.user_id == "test-user"


class TestConnectorInterfaceConformance:
    """Verify that MockBankConnector conforms to the BankConnector interface."""

    def test_mock_provides_required_attributes(self):
        conn = MockBankConnector({"user_id": "test"})
        assert conn.name == "mock"
        assert conn.display_name == "Mock Bank (Dev)"
        assert conn.supports_refresh is True
        assert conn.supports_oauth is False

    def test_mock_auth_status_conforms(self):
        conn = MockBankConnector({"user_id": "test", "mode": "default"})
        status = conn.get_auth_status()
        assert isinstance(status, ConnectorAuthStatus)
        assert hasattr(status, "connected")
        assert hasattr(status, "user_id")
        assert hasattr(status, "institution_name")
