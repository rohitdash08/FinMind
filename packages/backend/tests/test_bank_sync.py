"""Tests for Bank Sync Connector Architecture (issue #75)."""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from app.services.bank_sync import (
    BankConnector,
    ConnectorConfig,
    SyncTransaction,
    SyncResult,
    CSVFileConnector,
    MockBankConnector,
    PlaidConnector,
    create_connector,
    list_connectors,
    get_connector_class,
    register_connector,
)

try:
    import redis as _redis_lib
    _r = _redis_lib.Redis.from_url("redis://localhost:6379/15")
    _r.ping()
    _redis_available = True
except Exception:
    _redis_available = False

requires_redis = pytest.mark.skipif(
    not _redis_available, reason="Redis not available"
)

SAMPLE_CSV = """date,amount,description
2026-01-15,-50.00,Grocery Store
2026-01-16,1000.00,Salary Deposit
2026-01-17,-25.50,Gas Station
2026-01-18,-12.99,Netflix
"""


# -----------------------------------------------------------------------
# Unit tests for data types
# -----------------------------------------------------------------------

class TestSyncTransaction:
    def test_to_dict(self):
        txn = SyncTransaction(
            external_id="abc123",
            date=date(2026, 1, 15),
            amount=Decimal("50.00"),
            currency="USD",
            description="Grocery",
        )
        d = txn.to_dict()
        assert d["external_id"] == "abc123"
        assert d["date"] == "2026-01-15"
        assert d["amount"] == "50.00"
        assert d["currency"] == "USD"

    def test_balance_optional(self):
        txn = SyncTransaction("x", date.today(), Decimal("10"), "USD", "test")
        d = txn.to_dict()
        assert d["balance"] is None


class TestSyncResult:
    def test_to_dict(self):
        result = SyncResult(
            connector_name="mock_bank",
            account_id="acc1",
            synced_at="2026-01-15T00:00:00",
        )
        d = result.to_dict()
        assert d["connector"] == "mock_bank"
        assert d["success"] is True
        assert d["transactions"] == []


# -----------------------------------------------------------------------
# Connector registry tests
# -----------------------------------------------------------------------

class TestConnectorRegistry:
    def test_list_connectors_includes_builtins(self):
        connectors = list_connectors()
        names = [c["name"] for c in connectors]
        assert "csv_file" in names
        assert "mock_bank" in names
        assert "plaid" in names

    def test_get_connector_class(self):
        cls = get_connector_class("mock_bank")
        assert cls == MockBankConnector

    def test_get_unknown_connector_returns_none(self):
        cls = get_connector_class("unknown_xyz")
        assert cls is None

    def test_create_connector_factory(self):
        connector = create_connector("mock_bank", {"api_key": "test"})
        assert connector is not None
        assert isinstance(connector, MockBankConnector)

    def test_create_unknown_connector_returns_none(self):
        connector = create_connector("doesnt_exist", {})
        assert connector is None

    def test_register_new_connector(self):
        @register_connector
        class TestConnector(BankConnector):
            NAME = "test_connector_unit"
            def validate_credentials(self): return True
            def fetch_transactions(self, account_id, since=None, until=None): return []

        cls = get_connector_class("test_connector_unit")
        assert cls == TestConnector

    def test_connector_metadata_in_list(self):
        connectors = list_connectors()
        mock = next(c for c in connectors if c["name"] == "mock_bank")
        assert mock["supports_balance"] is True
        assert mock["supports_refresh"] is True


# -----------------------------------------------------------------------
# CSV connector tests
# -----------------------------------------------------------------------

class TestCSVConnector:
    def _make_connector(self, csv_content=SAMPLE_CSV, delimiter=","):
        config = ConnectorConfig(
            connector_name="csv_file",
            options={"csv_content": csv_content, "delimiter": delimiter, "currency": "USD"},
        )
        return CSVFileConnector(config)

    def test_validate_always_true(self):
        conn = self._make_connector()
        assert conn.validate_credentials() is True

    def test_fetch_all_transactions(self):
        conn = self._make_connector()
        txns = conn.fetch_transactions("acc1")
        assert len(txns) == 4

    def test_transaction_types(self):
        conn = self._make_connector()
        txns = conn.fetch_transactions("acc1")
        expense_txns = [t for t in txns if t.transaction_type == "expense"]
        income_txns = [t for t in txns if t.transaction_type == "income"]
        assert len(expense_txns) == 3
        assert len(income_txns) == 1

    def test_date_filter_since(self):
        conn = self._make_connector()
        txns = conn.fetch_transactions("acc1", since=date(2026, 1, 17))
        assert len(txns) == 2

    def test_date_filter_until(self):
        conn = self._make_connector()
        txns = conn.fetch_transactions("acc1", until=date(2026, 1, 16))
        assert len(txns) == 2

    def test_empty_csv_returns_empty(self):
        conn = self._make_connector(csv_content="")
        txns = conn.fetch_transactions("acc1")
        assert txns == []

    def test_amount_is_absolute(self):
        conn = self._make_connector()
        txns = conn.fetch_transactions("acc1")
        for t in txns:
            assert t.amount >= 0


# -----------------------------------------------------------------------
# Mock bank connector tests
# -----------------------------------------------------------------------

class TestMockBankConnector:
    def _make_connector(self):
        config = ConnectorConfig(
            connector_name="mock_bank",
            credentials={"api_key": "test-key"},
        )
        return MockBankConnector(config)

    def test_validate_with_api_key(self):
        conn = self._make_connector()
        assert conn.validate_credentials() is True

    def test_validate_without_api_key(self):
        config = ConnectorConfig("mock_bank", credentials={})
        conn = MockBankConnector(config)
        assert conn.validate_credentials() is False

    def test_fetch_returns_transactions(self):
        conn = self._make_connector()
        since = date(2026, 1, 1)
        until = date(2026, 1, 31)
        txns = conn.fetch_transactions("acc1", since=since, until=until)
        assert len(txns) > 0

    def test_get_balance(self):
        conn = self._make_connector()
        balance = conn.get_balance("acc1")
        assert balance == Decimal("1234.56")

    def test_refresh_returns_sync_result(self):
        conn = self._make_connector()
        result = conn.refresh("acc1")
        assert result.success is True
        assert result.connector_name == "mock_bank"
        assert len(result.transactions) > 0


# -----------------------------------------------------------------------
# Plaid connector tests
# -----------------------------------------------------------------------

class TestPlaidConnector:
    def test_validate_with_full_credentials(self):
        config = ConnectorConfig(
            "plaid",
            credentials={"client_id": "x", "secret": "y", "access_token": "z"},
        )
        conn = PlaidConnector(config)
        assert conn.validate_credentials() is True

    def test_validate_missing_credential(self):
        config = ConnectorConfig(
            "plaid",
            credentials={"client_id": "x"},
        )
        conn = PlaidConnector(config)
        assert conn.validate_credentials() is False


# -----------------------------------------------------------------------
# API tests (require Redis)
# -----------------------------------------------------------------------

@requires_redis
class TestBankSyncAPI:
    def test_list_connectors(self, client):
        resp = client.get("/bank-sync/connectors")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "connectors" in data
        names = [c["name"] for c in data["connectors"]]
        assert "mock_bank" in names

    def test_validate_mock_connector(self, client, auth_header):
        resp = client.post("/bank-sync/validate", json={
            "connector": "mock_bank",
            "credentials": {"api_key": "test"},
        }, headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["valid"] is True

    def test_validate_unknown_connector(self, client, auth_header):
        resp = client.post("/bank-sync/validate", json={
            "connector": "totally_unknown",
            "credentials": {},
        }, headers=auth_header)
        assert resp.status_code == 404

    def test_import_mock_transactions(self, client, auth_header):
        resp = client.post("/bank-sync/import", json={
            "connector": "mock_bank",
            "account_id": "test_account",
            "credentials": {"api_key": "test-key"},
        }, headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["connector"] == "mock_bank"
        assert len(data["transactions"]) > 0

    def test_import_csv_connector(self, client, auth_header):
        resp = client.post("/bank-sync/import", json={
            "connector": "csv_file",
            "account_id": "csv_acc",
            "credentials": {},
            "options": {"csv_content": SAMPLE_CSV},
        }, headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["new_count"] == 4

    def test_balance_mock_connector(self, client, auth_header):
        resp = client.post("/bank-sync/balance", json={
            "connector": "mock_bank",
            "account_id": "acc1",
            "credentials": {"api_key": "test"},
        }, headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["balance"] == "1234.56"

    def test_balance_csv_connector_unsupported(self, client, auth_header):
        resp = client.post("/bank-sync/balance", json={
            "connector": "csv_file",
            "credentials": {},
        }, headers=auth_header)
        assert resp.status_code == 400