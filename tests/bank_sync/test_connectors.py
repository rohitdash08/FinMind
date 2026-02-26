"""Tests for connectors: mock, csv, registry."""

import csv
import os
import tempfile
from datetime import datetime, timedelta

import pytest

from connectors.base import BankConnector, ConnectorError
from connectors.mock import MockConnector
from connectors.csv_import import CSVConnector
from connectors.registry import ConnectorRegistry, get_registry
from models.transaction import AccountType, TransactionType


class TestMockConnector:
    def setup_method(self):
        self.conn = MockConnector(connector_id="test-mock")

    def test_not_connected_raises(self):
        with pytest.raises(ConnectorError, match="not connected"):
            self.conn.get_accounts()

    def test_connect_disconnect(self):
        self.conn.connect()
        assert self.conn.is_connected is True
        assert len(self.conn.get_accounts()) == 3
        self.conn.disconnect()
        assert self.conn.is_connected is False

    def test_get_accounts(self):
        self.conn.connect()
        accounts = self.conn.get_accounts()
        types = {a.account_type for a in accounts}
        assert AccountType.CHECKING in types
        assert AccountType.SAVINGS in types
        assert AccountType.CREDIT in types

    def test_get_balance(self):
        self.conn.connect()
        accounts = self.conn.get_accounts()
        for acct in accounts:
            bal = self.conn.get_balance(acct.account_id)
            assert bal.account_id == acct.account_id
            assert isinstance(bal.current, float)

    def test_get_balance_invalid_account(self):
        self.conn.connect()
        with pytest.raises(ConnectorError, match="not found"):
            self.conn.get_balance("nonexistent")

    def test_import_transactions(self):
        self.conn.connect()
        end = datetime.utcnow()
        start = end - timedelta(days=7)
        txns = self.conn.import_transactions(start, end)
        assert len(txns) > 0
        for t in txns:
            assert start <= t.date <= end.replace(hour=23, minute=59)
            assert t.transaction_id
            assert t.description

    def test_import_single_account(self):
        self.conn.connect()
        acct = self.conn.get_accounts()[0]
        end = datetime.utcnow()
        start = end - timedelta(days=3)
        txns = self.conn.import_transactions(start, end, account_id=acct.account_id)
        assert all(t.account_id == acct.account_id for t in txns)

    def test_import_invalid_account(self):
        self.conn.connect()
        with pytest.raises(ConnectorError):
            self.conn.import_transactions(datetime.utcnow(), datetime.utcnow(), account_id="bad")

    def test_refresh(self):
        self.conn.connect()
        # Do initial import to set last_refresh
        end = datetime.utcnow()
        start = end - timedelta(days=1)
        self.conn.import_transactions(start, end)
        # Refresh should return transactions
        txns = self.conn.refresh()
        assert isinstance(txns, list)

    def test_deterministic_data(self):
        """Same connector_id should produce same accounts."""
        c1 = MockConnector(connector_id="seed-test")
        c2 = MockConnector(connector_id="seed-test")
        c1.connect()
        c2.connect()
        a1 = [a.account_id for a in c1.get_accounts()]
        a2 = [a.account_id for a in c2.get_accounts()]
        assert a1 == a2

    def test_repr(self):
        assert "MockConnector" in repr(self.conn)

    def test_properties(self):
        assert self.conn.name == "Mock Bank"
        assert self.conn.connector_type == "mock"


class TestCSVConnector:
    def _write_csv(self, rows, headers=None):
        """Helper to write a temp CSV file."""
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.writer(f)
            if headers:
                writer.writerow(headers)
            writer.writerows(rows)
        return path

    def test_basic_import(self):
        path = self._write_csv(
            [
                ["2025-01-15", "-45.99", "Grocery Store"],
                ["2025-01-16", "2000.00", "Payroll"],
                ["2025-01-17", "-12.50", "Coffee Shop"],
            ],
            headers=["date", "amount", "description"],
        )
        try:
            conn = CSVConnector(config={"file_path": path})
            conn.connect()
            assert conn.is_connected
            accounts = conn.get_accounts()
            assert len(accounts) == 1

            txns = conn.import_transactions(datetime(2025, 1, 1), datetime(2025, 12, 31))
            assert len(txns) == 3
            assert txns[0].amount == -45.99
            assert txns[1].amount == 2000.00
            conn.disconnect()
        finally:
            os.unlink(path)

    def test_date_formats(self):
        path = self._write_csv(
            [
                ["01/15/2025", "-10.00", "Test1"],
                ["01/16/2025", "-20.00", "Test2"],
            ],
            headers=["date", "amount", "description"],
        )
        try:
            conn = CSVConnector(config={"file_path": path})
            conn.connect()
            txns = conn.import_transactions(datetime(2025, 1, 1), datetime(2025, 12, 31))
            assert len(txns) == 2
            assert txns[0].date.month == 1
            assert txns[0].date.day == 15
            conn.disconnect()
        finally:
            os.unlink(path)

    def test_currency_symbols(self):
        path = self._write_csv(
            [["2025-01-15", "$-1,234.56", "Big Purchase"]],
            headers=["date", "amount", "description"],
        )
        try:
            conn = CSVConnector(config={"file_path": path})
            conn.connect()
            txns = conn.import_transactions(datetime(2025, 1, 1), datetime(2025, 12, 31))
            assert len(txns) == 1
            assert txns[0].amount == -1234.56
            conn.disconnect()
        finally:
            os.unlink(path)

    def test_load_file_after_connect(self):
        path = self._write_csv(
            [["2025-03-01", "-5.00", "Snack"]],
            headers=["date", "amount", "description"],
        )
        try:
            conn = CSVConnector()
            conn.connect()
            count = conn.load_file(path)
            assert count == 1
            conn.disconnect()
        finally:
            os.unlink(path)

    def test_missing_file(self):
        conn = CSVConnector(config={"file_path": "/nonexistent/file.csv"})
        with pytest.raises(ConnectorError, match="not found"):
            conn.connect()

    def test_balance_from_transactions(self):
        path = self._write_csv(
            [
                ["2025-01-01", "1000.00", "Deposit"],
                ["2025-01-02", "-250.00", "Withdrawal"],
            ],
            headers=["date", "amount", "description"],
        )
        try:
            conn = CSVConnector(config={"file_path": path})
            conn.connect()
            acct = conn.get_accounts()[0]
            bal = conn.get_balance(acct.account_id)
            assert bal.current == 750.0
            conn.disconnect()
        finally:
            os.unlink(path)

    def test_refresh_reloads(self):
        path = self._write_csv(
            [["2025-01-01", "-10.00", "Item"]],
            headers=["date", "amount", "description"],
        )
        try:
            conn = CSVConnector(config={"file_path": path})
            conn.connect()
            txns = conn.refresh()
            assert len(txns) == 1
            conn.disconnect()
        finally:
            os.unlink(path)

    def test_properties(self):
        conn = CSVConnector()
        assert conn.name == "CSV Import"
        assert conn.connector_type == "csv"


class TestConnectorRegistry:
    def test_auto_register(self):
        reg = ConnectorRegistry()
        reg.auto_register()
        assert "mock" in reg
        assert "plaid" in reg
        assert "csv" in reg
        assert len(reg) == 3

    def test_create_mock(self):
        reg = ConnectorRegistry()
        reg.auto_register()
        conn = reg.create("mock", connector_id="r-mock")
        assert isinstance(conn, BankConnector)
        assert conn.connector_id == "r-mock"

    def test_unknown_type(self):
        reg = ConnectorRegistry()
        with pytest.raises(ConnectorError, match="Unknown connector type"):
            reg.create("nonexistent")

    def test_register_invalid_class(self):
        reg = ConnectorRegistry()
        with pytest.raises(TypeError):
            reg.register("bad", str)  # type: ignore

    def test_unregister(self):
        reg = ConnectorRegistry()
        reg.auto_register()
        assert reg.unregister("mock") is True
        assert "mock" not in reg
        assert reg.unregister("mock") is False

    def test_available_types(self):
        reg = ConnectorRegistry()
        reg.auto_register()
        types = reg.available_types
        assert types == ["csv", "mock", "plaid"]

    def test_get_class(self):
        reg = ConnectorRegistry()
        reg.auto_register()
        cls = reg.get_class("mock")
        assert cls is MockConnector

    def test_default_registry(self):
        reg = get_registry()
        assert "mock" in reg

    def test_repr(self):
        reg = ConnectorRegistry()
        reg.auto_register()
        assert "ConnectorRegistry" in repr(reg)
