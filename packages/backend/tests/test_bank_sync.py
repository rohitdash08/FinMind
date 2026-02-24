"""Tests for the bank-sync connector architecture.

Covers:
- Connector interface / mock connector
- Connector registry
- Bank-sync service layer (import, refresh, dedup, disconnect)
- Bank-sync API endpoints
"""

from datetime import date

from app.connectors.base import (
    BankAccount,
    BankTransaction,
    SyncStatus,
)
from app.connectors.mock import MockBankConnector
from app.connectors.registry import ConnectorRegistry


# ======================================================================
# Unit: Connector interface & mock connector
# ======================================================================


class TestMockConnector:
    def test_authenticate_success(self):
        conn = MockBankConnector()
        assert conn.authenticate({}) is True

    def test_authenticate_fail(self):
        conn = MockBankConnector({"fail_auth": True})
        assert conn.authenticate({}) is False

    def test_get_accounts_returns_list(self):
        conn = MockBankConnector()
        conn.authenticate({})
        accounts = conn.get_accounts()
        assert len(accounts) >= 1
        assert isinstance(accounts[0], BankAccount)
        assert accounts[0].external_id
        assert accounts[0].currency == "INR"

    def test_get_accounts_requires_auth(self):
        conn = MockBankConnector()
        try:
            conn.get_accounts()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass

    def test_import_transactions(self):
        conn = MockBankConnector({"transaction_count": 10, "seed": "test"})
        conn.authenticate({})
        result = conn.import_transactions(
            "mock-sav-001",
            date(2026, 1, 1),
            date(2026, 1, 31),
        )
        assert result.status == SyncStatus.SUCCESS
        assert result.transaction_count > 0
        assert result.cursor == "2026-01-31"
        for txn in result.transactions:
            assert isinstance(txn, BankTransaction)
            assert txn.external_id
            assert txn.currency == "INR"

    def test_import_deterministic(self):
        """Same seed + params should produce identical transactions."""
        conn1 = MockBankConnector({"seed": "stable", "transaction_count": 5})
        conn1.authenticate({})
        r1 = conn1.import_transactions(
            "mock-sav-001", date(2026, 2, 1), date(2026, 2, 15)
        )

        conn2 = MockBankConnector({"seed": "stable", "transaction_count": 5})
        conn2.authenticate({})
        r2 = conn2.import_transactions(
            "mock-sav-001", date(2026, 2, 1), date(2026, 2, 15)
        )

        ids1 = [t.external_id for t in r1.transactions]
        ids2 = [t.external_id for t in r2.transactions]
        assert ids1 == ids2

    def test_refresh_without_cursor(self):
        conn = MockBankConnector({"transaction_count": 5})
        conn.authenticate({})
        result = conn.refresh("mock-sav-001", cursor=None)
        assert result.status == SyncStatus.SUCCESS
        assert result.transaction_count > 0
        assert result.cursor == date.today().isoformat()

    def test_refresh_with_cursor(self):
        conn = MockBankConnector({"transaction_count": 5})
        conn.authenticate({})
        result = conn.refresh("mock-sav-001", cursor="2026-02-01")
        assert result.status == SyncStatus.SUCCESS

    def test_disconnect(self):
        conn = MockBankConnector()
        conn.authenticate({})
        conn.disconnect()
        try:
            conn.get_accounts()
            assert False, "Expected RuntimeError after disconnect"
        except RuntimeError:
            pass


# ======================================================================
# Unit: Connector registry
# ======================================================================


class TestConnectorRegistry:
    def test_register_and_get(self):
        reg = ConnectorRegistry()
        reg.register("mock", MockBankConnector)
        cls = reg.get("mock")
        assert cls is MockBankConnector

    def test_case_insensitive(self):
        reg = ConnectorRegistry()
        reg.register("Mock", MockBankConnector)
        assert reg.get("MOCK") is MockBankConnector
        assert "mock" in reg

    def test_unknown_raises_key_error(self):
        reg = ConnectorRegistry()
        try:
            reg.get("nonexistent")
            assert False, "Expected KeyError"
        except KeyError:
            pass

    def test_available_sorted(self):
        reg = ConnectorRegistry()
        reg.register("beta", MockBankConnector)
        reg.register("alpha", MockBankConnector)
        assert reg.available() == ["alpha", "beta"]

    def test_len(self):
        reg = ConnectorRegistry()
        assert len(reg) == 0
        reg.register("x", MockBankConnector)
        assert len(reg) == 1


# ======================================================================
# Integration: API endpoints
# ======================================================================


def test_list_providers(client, auth_header):
    r = client.get("/bank-sync/providers", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "mock" in data["providers"]


def test_connect_creates_connection(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock", "credentials": {}},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["provider"] == "mock"
    assert data["status"] == "ACTIVE"
    assert data["account_name"]
    assert data["id"]


def test_connect_unknown_provider(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "nonexistent", "credentials": {}},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_connect_auth_failure(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={
            "provider": "mock",
            "credentials": {},
            "config": {"fail_auth": True},
        },
        headers=auth_header,
    )
    assert r.status_code == 401


def test_list_connections(client, auth_header):
    client.post(
        "/bank-sync/connect",
        json={"provider": "mock", "credentials": {}},
        headers=auth_header,
    )
    r = client.get("/bank-sync/connections", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 1


def test_import_transactions(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock", "credentials": {}},
        headers=auth_header,
    )
    conn_id = r.get_json()["id"]

    r = client.post(
        f"/bank-sync/connections/{conn_id}/import",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "credentials": {},
        },
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "SUCCESS"
    assert data["inserted"] > 0
    assert data["duplicates"] == 0


def test_import_prevents_duplicates(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={
            "provider": "mock",
            "credentials": {},
            "config": {"seed": "dedup", "transaction_count": 5},
        },
        headers=auth_header,
    )
    conn_id = r.get_json()["id"]
    payload = {
        "start_date": "2026-02-01",
        "end_date": "2026-02-15",
        "credentials": {},
        "config": {"seed": "dedup", "transaction_count": 5},
    }

    r1 = client.post(
        f"/bank-sync/connections/{conn_id}/import",
        json=payload,
        headers=auth_header,
    )
    assert r1.status_code == 200
    first = r1.get_json()
    assert first["inserted"] > 0

    r2 = client.post(
        f"/bank-sync/connections/{conn_id}/import",
        json=payload,
        headers=auth_header,
    )
    assert r2.status_code == 200
    second = r2.get_json()
    assert second["duplicates"] == first["inserted"]
    assert second["inserted"] == 0


def test_refresh_transactions(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock", "credentials": {}},
        headers=auth_header,
    )
    conn_id = r.get_json()["id"]

    r = client.post(
        f"/bank-sync/connections/{conn_id}/refresh",
        json={"credentials": {}},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "SUCCESS"
    assert data["inserted"] >= 0


def test_sync_logs(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock", "credentials": {}},
        headers=auth_header,
    )
    conn_id = r.get_json()["id"]

    client.post(
        f"/bank-sync/connections/{conn_id}/import",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "credentials": {},
        },
        headers=auth_header,
    )

    r = client.get(
        f"/bank-sync/connections/{conn_id}/logs",
        headers=auth_header,
    )
    assert r.status_code == 200
    logs = r.get_json()
    assert len(logs) >= 1
    assert logs[0]["sync_type"] == "import"
    assert logs[0]["status"] == "SUCCESS"


def test_disconnect(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock", "credentials": {}},
        headers=auth_header,
    )
    conn_id = r.get_json()["id"]

    r = client.delete(
        f"/bank-sync/connections/{conn_id}",
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.get("/bank-sync/connections", headers=auth_header)
    conns = r.get_json()
    matching = [c for c in conns if c["id"] == conn_id]
    assert matching[0]["status"] == "DISCONNECTED"


def test_import_missing_dates(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock", "credentials": {}},
        headers=auth_header,
    )
    conn_id = r.get_json()["id"]

    r = client.post(
        f"/bank-sync/connections/{conn_id}/import",
        json={"credentials": {}},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_connection_not_found(client, auth_header):
    r = client.post(
        "/bank-sync/connections/99999/import",
        json={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "credentials": {},
        },
        headers=auth_header,
    )
    assert r.status_code == 404


def test_refresh_not_found(client, auth_header):
    r = client.post(
        "/bank-sync/connections/99999/refresh",
        json={"credentials": {}},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_disconnect_not_found(client, auth_header):
    r = client.delete(
        "/bank-sync/connections/99999",
        headers=auth_header,
    )
    assert r.status_code == 404


def test_logs_not_found(client, auth_header):
    r = client.get(
        "/bank-sync/connections/99999/logs",
        headers=auth_header,
    )
    assert r.status_code == 404
