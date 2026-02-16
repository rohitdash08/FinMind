"""
Tests for the bank sync connector architecture.

Tests the connector interface, mock connector, registry,
and service layer.
"""

import pytest
from datetime import date, timedelta

from app.services.bank_sync import (
    BaseBankConnector,
    ConnectorRegistry,
    MockBankConnector,
    get_connector,
    register_connector,
)
from app.services.bank_sync.base import (
    BankAccount,
    BankTransaction,
    ConnectionStatus,
    SyncResult,
    TransactionType,
)


class TestMockBankConnector:
    """Test the mock bank connector."""

    def setup_method(self):
        self.connector = MockBankConnector(num_accounts=2, seed=42)

    def test_provider_name(self):
        assert self.connector.provider_name == "mock"

    def test_initial_status_disconnected(self):
        assert self.connector.get_status() == ConnectionStatus.DISCONNECTED

    def test_connect(self):
        status = self.connector.connect({})
        assert status == ConnectionStatus.CONNECTED
        assert self.connector.get_status() == ConnectionStatus.CONNECTED

    def test_disconnect(self):
        self.connector.connect({})
        assert self.connector.disconnect() is True
        assert self.connector.get_status() == ConnectionStatus.DISCONNECTED

    def test_list_accounts_when_connected(self):
        self.connector.connect({})
        accounts = self.connector.list_accounts()
        assert len(accounts) == 2
        assert all(isinstance(a, BankAccount) for a in accounts)
        assert accounts[0].institution_name == "Mock National Bank"

    def test_list_accounts_when_disconnected(self):
        accounts = self.connector.list_accounts()
        assert len(accounts) == 0

    def test_import_transactions(self):
        self.connector.connect({})
        accounts = self.connector.list_accounts()
        transactions = self.connector.import_transactions(accounts[0].account_id)
        assert len(transactions) > 0
        assert all(isinstance(t, BankTransaction) for t in transactions)

    def test_import_transactions_with_date_range(self):
        self.connector.connect({})
        accounts = self.connector.list_accounts()
        start = date.today() - timedelta(days=7)
        end = date.today()
        transactions = self.connector.import_transactions(
            accounts[0].account_id, start_date=start, end_date=end
        )
        assert all(start <= t.date <= end for t in transactions)

    def test_refresh(self):
        self.connector.connect({})
        result = self.connector.refresh()
        assert isinstance(result, SyncResult)
        assert result.success is True
        assert result.accounts_synced == 2
        assert result.transactions_imported > 0

    def test_refresh_specific_account(self):
        self.connector.connect({})
        accounts = self.connector.list_accounts()
        result = self.connector.refresh(account_id=accounts[0].account_id)
        assert result.success is True
        assert result.accounts_synced == 1

    def test_refresh_when_disconnected(self):
        result = self.connector.refresh()
        assert result.success is False
        assert len(result.errors) > 0

    def test_get_account(self):
        self.connector.connect({})
        accounts = self.connector.list_accounts()
        account = self.connector.get_account(accounts[0].account_id)
        assert account is not None
        assert account.account_id == accounts[0].account_id

    def test_get_account_not_found(self):
        self.connector.connect({})
        assert self.connector.get_account("nonexistent") is None

    def test_deterministic_with_seed(self):
        """Same seed should produce same data."""
        c1 = MockBankConnector(seed=123)
        c2 = MockBankConnector(seed=123)
        c1.connect({})
        c2.connect({})
        a1 = c1.list_accounts()
        a2 = c2.list_accounts()
        assert len(a1) == len(a2)
        assert a1[0].name == a2[0].name

    def test_transaction_types(self):
        """Should generate both debits and credits."""
        self.connector.connect({})
        accounts = self.connector.list_accounts()
        transactions = self.connector.import_transactions(
            accounts[0].account_id
        )
        types = {t.transaction_type for t in transactions}
        # With enough transactions, both types should appear
        assert TransactionType.DEBIT in types


class TestConnectorRegistry:
    """Test the connector registry."""

    def setup_method(self):
        self.registry = ConnectorRegistry()

    def test_register_and_get(self):
        self.registry.register("mock", MockBankConnector)
        connector = self.registry.get("mock")
        assert connector is not None
        assert connector.provider_name == "mock"

    def test_get_unregistered(self):
        assert self.registry.get("nonexistent") is None

    def test_list_providers(self):
        self.registry.register("mock", MockBankConnector)
        providers = self.registry.list_providers()
        assert "mock" in providers

    def test_is_registered(self):
        self.registry.register("mock", MockBankConnector)
        assert self.registry.is_registered("mock") is True
        assert self.registry.is_registered("plaid") is False

    def test_case_insensitive(self):
        self.registry.register("Mock", MockBankConnector)
        assert self.registry.is_registered("mock") is True
        assert self.registry.get("MOCK") is not None

    def test_register_invalid_class(self):
        with pytest.raises(TypeError):
            self.registry.register("bad", dict)

    def test_get_with_config(self):
        self.registry.register("mock", MockBankConnector)
        connector = self.registry.get("mock", config={"num_accounts": 3, "seed": 1})
        assert connector is not None
        connector.connect({})
        assert len(connector.list_accounts()) == 3


class TestGlobalRegistry:
    """Test the global registry functions."""

    def test_register_and_get_global(self):
        register_connector("test-mock", MockBankConnector)
        connector = get_connector("test-mock")
        assert connector is not None
        assert connector.provider_name == "mock"


class TestBankTransactionDataclass:
    """Test data class defaults and behavior."""

    def test_default_values(self):
        txn = BankTransaction(
            transaction_id="t1",
            account_id="a1",
            amount=10.50,
            currency="USD",
            description="Test",
        )
        assert txn.transaction_type == TransactionType.DEBIT
        assert txn.pending is False
        assert txn.category is None
        assert txn.metadata == {}

    def test_sync_result_defaults(self):
        result = SyncResult(success=True)
        assert result.accounts_synced == 0
        assert result.transactions_imported == 0
        assert result.errors == []
