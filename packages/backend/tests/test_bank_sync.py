from datetime import date

import pytest

from app.services import bank_sync
from app.services.bank_sync.base import (
    BankAccountInfo,
    BankConnector,
    BankTransaction,
    ConnectorError,
)


def test_mock_connector_is_registered():
    names = [c["provider"] for c in bank_sync.list_connectors()]
    assert "mock" in names


def test_mock_connector_connect_and_fetch():
    connector = bank_sync.get_connector("mock")
    accounts = connector.connect({"api_key": "test"})
    assert len(accounts) >= 1
    assert all(isinstance(a, BankAccountInfo) for a in accounts)

    txs = connector.fetch_transactions("mock-checking-001")
    assert len(txs) >= 1
    assert all(isinstance(t, BankTransaction) for t in txs)


def test_mock_connector_requires_credentials():
    connector = bank_sync.get_connector("mock")
    with pytest.raises(ConnectorError):
        connector.connect({})


def test_mock_connector_filters_by_since():
    connector = bank_sync.get_connector("mock")
    txs = connector.fetch_transactions(
        "mock-checking-001", since=date(2026, 2, 6)
    )
    assert all(t.date >= date(2026, 2, 6) for t in txs)


def test_get_connector_unknown():
    with pytest.raises(KeyError):
        bank_sync.get_connector("does-not-exist")


def test_register_custom_connector():
    @bank_sync.register_connector
    class CustomConnector(BankConnector):
        provider_name = "custom-test"
        display_name = "Custom"
        required_credentials = ("token",)

        def connect(self, credentials):
            return [BankAccountInfo(external_id="x", name="X")]

        def fetch_transactions(self, external_account_id, *, since=None):
            return []

    connector = bank_sync.get_connector("custom-test")
    assert isinstance(connector, CustomConnector)
    assert connector.connect({"token": "t"})[0].external_id == "x"


def test_list_connectors_endpoint(client, auth_header):
    r = client.get("/bank-sync/connectors", headers=auth_header)
    assert r.status_code == 200
    providers = [c["provider"] for c in r.get_json()]
    assert "mock" in providers


def test_link_account_requires_provider(client, auth_header):
    r = client.post("/bank-sync/accounts", json={}, headers=auth_header)
    assert r.status_code == 400


def test_link_account_unknown_provider(client, auth_header):
    r = client.post(
        "/bank-sync/accounts",
        json={"provider": "nope", "credentials": {}},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_link_account_invalid_credentials(client, auth_header):
    r = client.post(
        "/bank-sync/accounts",
        json={"provider": "mock", "credentials": {}},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_link_specific_account_then_import_then_refresh(client, auth_header):
    # Link only the checking account
    r = client.post(
        "/bank-sync/accounts",
        json={
            "provider": "mock",
            "credentials": {"api_key": "test"},
            "external_id": "mock-checking-001",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    accounts = r.get_json()
    assert len(accounts) == 1
    account_id = accounts[0]["id"]
    assert accounts[0]["external_id"] == "mock-checking-001"
    assert accounts[0]["last_synced_at"] is None

    # Initial import pulls everything
    r = client.post(
        f"/bank-sync/accounts/{account_id}/import", headers=auth_header
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "import"
    assert body["inserted"] == 3
    assert body["duplicates"] == 0
    assert body["last_synced_at"]

    # Verify expenses landed in the user's expense list
    r = client.get("/expenses", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 3
    descriptions = {it["description"] for it in items}
    assert "Coffee Shop" in descriptions
    assert "Payroll Deposit" in descriptions

    # Refresh re-runs the connector but dedupes against existing rows
    r = client.post(
        f"/bank-sync/accounts/{account_id}/refresh", headers=auth_header
    )
    assert r.status_code == 200
    refresh_body = r.get_json()
    assert refresh_body["mode"] == "refresh"
    assert refresh_body["inserted"] == 0
    assert refresh_body["duplicates"] >= 0

    # Account list reflects last_synced_at
    r = client.get("/bank-sync/accounts", headers=auth_header)
    assert r.status_code == 200
    listed = r.get_json()
    assert len(listed) == 1
    assert listed[0]["last_synced_at"] is not None


def test_link_all_accounts_default(client, auth_header):
    r = client.post(
        "/bank-sync/accounts",
        json={"provider": "mock", "credentials": {"api_key": "test"}},
        headers=auth_header,
    )
    assert r.status_code == 201
    accounts = r.get_json()
    assert len(accounts) == 2

    # Re-linking is idempotent: returns the same accounts, no duplicates
    r = client.post(
        "/bank-sync/accounts",
        json={"provider": "mock", "credentials": {"api_key": "test"}},
        headers=auth_header,
    )
    assert r.status_code == 201
    again = r.get_json()
    assert {a["id"] for a in again} == {a["id"] for a in accounts}


def test_unlink_account(client, auth_header):
    r = client.post(
        "/bank-sync/accounts",
        json={
            "provider": "mock",
            "credentials": {"api_key": "test"},
            "external_id": "mock-savings-002",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()[0]["id"]

    r = client.delete(
        f"/bank-sync/accounts/{account_id}", headers=auth_header
    )
    assert r.status_code == 200

    r = client.get("/bank-sync/accounts", headers=auth_header)
    assert r.get_json() == []


def test_import_unknown_account_returns_404(client, auth_header):
    r = client.post("/bank-sync/accounts/9999/import", headers=auth_header)
    assert r.status_code == 404
