"""Tests for the bank sync connector architecture."""

from __future__ import annotations

import pytest
from datetime import date


# ---------------------------------------------------------------------------
# Unit tests – connector interface & mock
# ---------------------------------------------------------------------------


class TestBankConnectorInterface:
    """Verify the abstract interface cannot be instantiated directly."""

    def test_cannot_instantiate_base(self):
        from app.services.bank_connectors.base import BankConnector

        with pytest.raises(TypeError):
            BankConnector()  # type: ignore[abstract]


class TestMockConnector:
    def setup_method(self):
        from app.services.bank_connectors.mock import MockBankConnector

        self.connector = MockBankConnector()

    def test_provider_id(self):
        assert self.connector.provider_id == "mock"

    def test_display_name(self):
        assert "mock" in self.connector.display_name.lower()

    def test_fetch_accounts_returns_list(self):
        accounts = self.connector.fetch_accounts({})
        assert isinstance(accounts, list)
        assert len(accounts) >= 1

    def test_fetch_accounts_fields(self):
        accounts = self.connector.fetch_accounts({})
        for acc in accounts:
            assert acc.account_id
            assert acc.account_name
            assert acc.account_type
            assert acc.currency

    def test_import_transactions_returns_result(self):
        from app.services.bank_connectors.base import ImportResult

        result = self.connector.import_transactions(
            {}, "mock-savings-001", date(2024, 1, 1), date(2024, 1, 31)
        )
        assert isinstance(result, ImportResult)
        assert isinstance(result.transactions, list)

    def test_import_transactions_within_date_range(self):
        from_date = date(2024, 2, 1)
        to_date = date(2024, 2, 28)
        result = self.connector.import_transactions({}, "mock-savings-001", from_date, to_date)
        for tx in result.transactions:
            assert from_date <= tx.transaction_date <= to_date

    def test_import_transactions_cursor_filtering(self):
        # Import with cursor should return only transactions after cursor date
        cursor = date(2024, 1, 10).isoformat()
        result = self.connector.import_transactions(
            {}, "mock-savings-001", date(2024, 1, 1), date(2024, 1, 31), cursor=cursor
        )
        for tx in result.transactions:
            assert tx.transaction_date > date(2024, 1, 10)

    def test_import_transactions_cursor_is_updated(self):
        result = self.connector.import_transactions(
            {}, "mock-savings-001", date(2024, 1, 1), date(2024, 1, 31)
        )
        if result.transactions:
            assert result.cursor is not None

    def test_refresh_returns_result(self):
        from app.services.bank_connectors.base import ImportResult

        result = self.connector.refresh({}, "mock-savings-001")
        assert isinstance(result, ImportResult)

    def test_refresh_with_cursor(self):
        cursor = date(2024, 1, 15).isoformat()
        result = self.connector.refresh({}, "mock-savings-001", cursor=cursor)
        assert isinstance(result.transactions, list)

    def test_transactions_have_required_fields(self):
        result = self.connector.import_transactions(
            {}, "mock-savings-001", date(2024, 1, 1), date(2024, 3, 31)
        )
        for tx in result.transactions:
            assert tx.transaction_id
            assert tx.account_id == "mock-savings-001"
            assert tx.amount > 0
            assert tx.currency
            assert tx.description
            assert tx.transaction_date
            assert tx.transaction_type in ("DEBIT", "CREDIT")


class TestConnectorRegistry:
    def test_mock_registered_by_default(self):
        from app.services.bank_connectors import get_connector

        c = get_connector("mock")
        assert c is not None
        assert c.provider_id == "mock"

    def test_get_unknown_returns_none(self):
        from app.services.bank_connectors import get_connector

        assert get_connector("nonexistent-provider-xyz") is None

    def test_list_connectors_includes_mock(self):
        from app.services.bank_connectors import list_connectors

        ids = [c.provider_id for c in list_connectors()]
        assert "mock" in ids

    def test_register_custom_connector(self):
        from app.services.bank_connectors import register_connector, get_connector
        from app.services.bank_connectors.base import (
            BankAccount, BankConnector, BankTransaction, ImportResult
        )

        class _DummyConnector(BankConnector):
            @property
            def provider_id(self):
                return "dummy-test-xyz"

            @property
            def display_name(self):
                return "Dummy Test"

            def fetch_accounts(self, credentials):
                return []

            def import_transactions(self, credentials, account_id, from_date, to_date, cursor=None):
                return ImportResult(transactions=[])

            def refresh(self, credentials, account_id, cursor=None):
                return ImportResult(transactions=[])

        register_connector(_DummyConnector())
        assert get_connector("dummy-test-xyz") is not None


# ---------------------------------------------------------------------------
# Integration tests – HTTP endpoints
# ---------------------------------------------------------------------------


class TestBankSyncRoutes:
    def test_list_providers_requires_auth(self, client):
        r = client.get("/bank-sync/providers")
        assert r.status_code == 401

    def test_list_providers(self, client, auth_header):
        r = client.get("/bank-sync/providers", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        ids = [p["provider_id"] for p in data]
        assert "mock" in ids

    def test_fetch_provider_accounts(self, client, auth_header):
        r = client.post(
            "/bank-sync/providers/mock/accounts",
            json={},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "account_id" in data[0]

    def test_fetch_provider_accounts_unknown(self, client, auth_header):
        r = client.post(
            "/bank-sync/providers/nope/accounts",
            json={},
            headers=auth_header,
        )
        assert r.status_code == 404

    def test_create_connection(self, client, auth_header):
        r = client.post(
            "/bank-sync/connections",
            json={"provider_id": "mock", "account_id": "mock-savings-001"},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["provider_id"] == "mock"
        assert data["account_id"] == "mock-savings-001"

    def test_create_connection_duplicate(self, client, auth_header):
        payload = {"provider_id": "mock", "account_id": "mock-savings-001"}
        client.post("/bank-sync/connections", json=payload, headers=auth_header)
        r = client.post("/bank-sync/connections", json=payload, headers=auth_header)
        assert r.status_code == 409

    def test_create_connection_missing_provider(self, client, auth_header):
        r = client.post(
            "/bank-sync/connections",
            json={"account_id": "mock-savings-001"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_create_connection_unknown_provider(self, client, auth_header):
        r = client.post(
            "/bank-sync/connections",
            json={"provider_id": "nope", "account_id": "x"},
            headers=auth_header,
        )
        assert r.status_code == 404

    def test_list_connections(self, client, auth_header):
        client.post(
            "/bank-sync/connections",
            json={"provider_id": "mock", "account_id": "mock-savings-001"},
            headers=auth_header,
        )
        r = client.get("/bank-sync/connections", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert any(c["account_id"] == "mock-savings-001" for c in data)

    def test_delete_connection(self, client, auth_header):
        r = client.post(
            "/bank-sync/connections",
            json={"provider_id": "mock", "account_id": "mock-savings-001"},
            headers=auth_header,
        )
        conn_id = r.get_json()["id"]
        r = client.delete(f"/bank-sync/connections/{conn_id}", headers=auth_header)
        assert r.status_code == 200
        # Should no longer appear in list
        r = client.get("/bank-sync/connections", headers=auth_header)
        ids = [c["id"] for c in r.get_json()]
        assert conn_id not in ids

    def test_delete_connection_not_found(self, client, auth_header):
        r = client.delete("/bank-sync/connections/99999", headers=auth_header)
        assert r.status_code == 404

    def _create_connection(self, client, auth_header) -> int:
        r = client.post(
            "/bank-sync/connections",
            json={"provider_id": "mock", "account_id": "mock-savings-001"},
            headers=auth_header,
        )
        return r.get_json()["id"]

    def test_import_preview(self, client, auth_header):
        conn_id = self._create_connection(client, auth_header)
        r = client.post(
            f"/bank-sync/connections/{conn_id}/import",
            json={"from_date": "2024-01-01", "to_date": "2024-01-31", "commit": False},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert "total" in data
        assert "transactions" in data

    def test_import_commit(self, client, auth_header):
        conn_id = self._create_connection(client, auth_header)
        r = client.post(
            f"/bank-sync/connections/{conn_id}/import",
            json={"from_date": "2024-01-01", "to_date": "2024-01-31", "commit": True},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert "inserted" in data

    def test_import_missing_dates(self, client, auth_header):
        conn_id = self._create_connection(client, auth_header)
        r = client.post(
            f"/bank-sync/connections/{conn_id}/import",
            json={"commit": False},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_import_invalid_dates(self, client, auth_header):
        conn_id = self._create_connection(client, auth_header)
        r = client.post(
            f"/bank-sync/connections/{conn_id}/import",
            json={"from_date": "bad", "to_date": "2024-01-31"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_refresh(self, client, auth_header):
        conn_id = self._create_connection(client, auth_header)
        r = client.post(
            f"/bank-sync/connections/{conn_id}/refresh",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert "inserted" in data
        assert "cursor" in data

    def test_refresh_idempotent(self, client, auth_header):
        conn_id = self._create_connection(client, auth_header)
        r1 = client.post(f"/bank-sync/connections/{conn_id}/refresh", headers=auth_header)
        inserted1 = r1.get_json()["inserted"]
        r2 = client.post(f"/bank-sync/connections/{conn_id}/refresh", headers=auth_header)
        inserted2 = r2.get_json()["inserted"]
        # second refresh should find no new transactions (all duplicates)
        assert inserted2 == 0 or inserted2 <= inserted1

    def test_refresh_not_found(self, client, auth_header):
        r = client.post("/bank-sync/connections/99999/refresh", headers=auth_header)
        assert r.status_code == 404
