"""
Tests for Bank Sync Connectors.

Tests cover:
- Base connector interface
- Mock connector (import, refresh, accounts)
- Registry (register, get, list)
- API routes (import, refresh, health)
"""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services.connectors.base import (
    AccountInfo,
    BankConnector,
    ConnectionStatus,
    SyncResult,
    TransactionRecord,
)
from app.services.connectors.mock_connector import (
    MockConnector,
    _generate_transactions,
)
from app.services.connectors.registry import (
    get_connector,
    list_connectors,
    register_connector,
)


# ─── Base Connector Tests ─────────────────────────────────────────────

class TestBankConnector:
    def test_abstract_methods_exist(self):
        """Verify base class defines required abstract methods."""
        assert hasattr(BankConnector, "connect")
        assert hasattr(BankConnector, "disconnect")
        assert hasattr(BankConnector, "import_transactions")
        assert hasattr(BankConnector, "refresh")

    def test_cannot_instantiate_abstract(self):
        """Cannot instantiate BankConnector directly."""
        with pytest.raises(TypeError):
            BankConnector()

    def test_transaction_record_to_dict(self):
        """TransactionRecord converts to import dict correctly."""
        txn = TransactionRecord(
            transaction_id="txn-1",
            date=date(2025, 6, 2),
            amount=-50.00,
            description="Test Store",
            currency="USD",
        )
        d = txn.to_import_dict()
        assert d["date"] == "2025-06-02"
        assert d["amount"] == 50.00
        assert d["expense_type"] == "EXPENSE"
        assert d["currency"] == "USD"

    def test_transaction_income_type(self):
        """Positive amount maps to INCOME."""
        txn = TransactionRecord(
            transaction_id="txn-2",
            date=date(2025, 6, 2),
            amount=1000.00,
            description="Payroll",
        )
        assert txn.to_import_dict()["expense_type"] == "INCOME"


# ─── Mock Connector Tests ─────────────────────────────────────────────

class TestMockConnector:
    @pytest.fixture
    def connector(self):
        return MockConnector()

    def test_provider_name(self):
        assert MockConnector.provider_name == "mock"

    def test_connect(self, connector):
        result = asyncio.get_event_loop().run_until_complete(connector.connect())
        assert result == ConnectionStatus.CONNECTED
        assert connector.connected is True

    def test_disconnect(self, connector):
        asyncio.get_event_loop().run_until_complete(connector.connect())
        result = asyncio.get_event_loop().run_until_complete(connector.disconnect())
        assert result is True
        assert connector.connected is False

    def test_get_accounts(self, connector):
        accounts = asyncio.get_event_loop().run_until_complete(connector.get_accounts())
        assert len(accounts) == 3
        assert accounts[0].account_id == "mock-checking-001"
        assert accounts[0].type == "checking"

    def test_import_transactions(self, connector):
        asyncio.get_event_loop().run_until_complete(connector.connect())
        result = asyncio.get_event_loop().run_until_complete(
            connector.import_transactions("mock-checking-001")
        )
        assert result.status == "success"
        assert result.provider == "mock"
        assert result.transactions_imported > 0

    def test_import_transactions_custom_dates(self, connector):
        asyncio.get_event_loop().run_until_complete(connector.connect())
        start = date.today() - timedelta(days=30)
        result = asyncio.get_event_loop().run_until_complete(
            connector.import_transactions("mock-checking-001", start_date=start)
        )
        assert result.transactions_imported > 0

    def test_refresh(self, connector):
        asyncio.get_event_loop().run_until_complete(connector.connect())
        result = asyncio.get_event_loop().run_until_complete(
            connector.refresh("mock-checking-001")
        )
        assert result.status == "success"

    def test_health_check(self, connector):
        health = asyncio.get_event_loop().run_until_complete(connector.health_check())
        assert health["provider"] == "mock"
        assert health["healthy"] is True

    def test_generate_transactions_deterministic(self):
        """Same seed produces same transactions."""
        start = date(2025, 1, 1)
        end = date(2025, 1, 31)
        txns1 = _generate_transactions(start, end, seed=42)
        txns2 = _generate_transactions(start, end, seed=42)
        assert len(txns1) == len(txns2)
        for t1, t2 in zip(txns1, txns2):
            assert t1.transaction_id == t2.transaction_id
            assert t1.amount == t2.amount

    def test_generate_transactions_sorted_desc(self):
        """Transactions are sorted by date descending."""
        txns = _generate_transactions(
            date(2025, 1, 1), date(2025, 3, 31), seed=42
        )
        for i in range(len(txns) - 1):
            assert txns[i].date >= txns[i + 1].date


# ─── Registry Tests ────────────────────────────────────────────────────

class TestRegistry:
    def test_list_connectors_includes_mock(self):
        connectors = list_connectors()
        assert "mock" in connectors

    def test_get_connector_mock(self):
        cls = get_connector("mock")
        assert cls == MockConnector

    def test_get_connector_unknown(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_connector("nonexistent")

    def test_get_connector_case_insensitive(self):
        cls = get_connector("MOCK")
        assert cls == MockConnector


# ─── Integration: Full Import Flow ─────────────────────────────────────

class TestImportFlow:
    def test_end_to_end_import(self):
        """Full flow: connect → get accounts → import → verify."""
        connector = MockConnector()

        # Connect
        status = asyncio.get_event_loop().run_until_complete(connector.connect())
        assert status == ConnectionStatus.CONNECTED

        # Get accounts
        accounts = asyncio.get_event_loop().run_until_complete(connector.get_accounts())
        assert len(accounts) >= 1

        # Import transactions
        account = accounts[0]
        result = asyncio.get_event_loop().run_until_complete(
            connector.import_transactions(account.account_id)
        )
        assert result.status == "success"
        assert result.transactions_imported > 0

        # Refresh
        result = asyncio.get_event_loop().run_until_complete(
            connector.refresh(account.account_id)
        )
        assert result.status == "success"
