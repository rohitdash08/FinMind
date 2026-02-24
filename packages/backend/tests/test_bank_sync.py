"""Tests for the Bank Sync Connector Architecture.

Covers:
- Connector interface and registry
- Mock connector (consent, accounts, transactions, refresh)
- Bank sync service (connect, confirm, sync, refresh, disconnect)
- API endpoints
- Cursor-based incremental refresh
- Duplicate detection
- Error handling
"""

from datetime import date, timedelta

from app.connectors import (
    BankAccount,
    SyncResult,
    Transaction,
    get_connector,
    list_providers,
)
from app.connectors.mock import MockConnector
from app.extensions import db
from app.models import BankConnection


# ---------------------------------------------------------------------------
# Connector registry
# ---------------------------------------------------------------------------


def test_mock_connector_registered():
    providers = list_providers()
    assert "mock" in providers


def test_setu_aa_connector_registered(app_fixture):
    providers = list_providers()
    assert "setu_aa" in providers


def test_get_connector_returns_correct_type():
    conn = get_connector("mock")
    assert isinstance(conn, MockConnector)
    assert conn.provider_name == "mock"


def test_get_connector_unknown_raises():
    try:
        get_connector("nonexistent")
        assert False, "Should have raised"
    except ValueError as exc:
        assert "Unknown provider" in str(exc)


# ---------------------------------------------------------------------------
# Mock connector unit tests
# ---------------------------------------------------------------------------


def test_mock_create_consent():
    c = MockConnector()
    result = c.create_consent(user_id=1)
    assert result["consent_handle"].startswith("mock-consent-")
    assert result["status"] == "approved"


def test_mock_check_consent_status():
    c = MockConnector()
    assert c.check_consent_status("any-handle") == "approved"


def test_mock_fetch_accounts():
    c = MockConnector()
    accounts = c.fetch_accounts("any-handle")
    assert len(accounts) == 2
    assert all(isinstance(a, BankAccount) for a in accounts)
    assert accounts[0].currency == "INR"
    assert "HDFC" in accounts[0].label


def test_mock_fetch_transactions():
    c = MockConnector()
    result = c.fetch_transactions(
        "handle",
        "mock-savings-001",
        date(2026, 1, 1),
        date(2026, 1, 7),
    )
    assert isinstance(result, SyncResult)
    assert len(result.transactions) > 0
    assert result.cursor == "2026-01-07"
    for txn in result.transactions:
        assert isinstance(txn, Transaction)
        assert txn.currency == "INR"
        assert txn.txn_id.startswith("mock-")


def test_mock_refresh_with_cursor():
    c = MockConnector()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    result = c.refresh_transactions("handle", "mock-savings-001", yesterday)
    assert isinstance(result, SyncResult)
    assert result.cursor == date.today().isoformat()


def test_mock_refresh_no_cursor():
    c = MockConnector()
    result = c.refresh_transactions("handle", "mock-savings-001", None)
    assert isinstance(result, SyncResult)
    assert len(result.transactions) > 0


def test_mock_transactions_have_indian_data():
    c = MockConnector()
    result = c.fetch_transactions(
        "handle",
        "mock-savings-001",
        date(2026, 1, 1),
        date(2026, 1, 15),
    )
    descriptions = [t.description for t in result.transactions]
    combined = " ".join(descriptions)
    indian_keywords = ["Swiggy", "Zomato", "Amazon.in", "Jio", "UPI", "NEFT"]
    found = any(k in combined for k in indian_keywords)
    assert found, f"Expected Indian transaction data, got: {combined[:200]}"


def test_mock_transactions_include_income():
    c = MockConnector()
    result = c.fetch_transactions(
        "handle",
        "mock-savings-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
    )
    types = {t.expense_type for t in result.transactions}
    assert "INCOME" in types
    assert "EXPENSE" in types


# ---------------------------------------------------------------------------
# Bank sync service — via API endpoints
# ---------------------------------------------------------------------------


def test_list_providers_endpoint(client, auth_header):
    r = client.get("/bank-sync/providers", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "mock" in data["providers"]
    assert "setu_aa" in data["providers"]


def test_connect_with_mock(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock"},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["connection_id"] is not None
    assert data["status"] in ("approved", "pending")
    assert data["consent_handle"].startswith("mock-consent-")


def test_connect_missing_provider(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_connect_unknown_provider(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "nonexistent"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_full_connection_flow(client, auth_header, app_fixture):
    # 1. Connect
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock"},
        headers=auth_header,
    )
    assert r.status_code == 201
    conn_id = r.get_json()["connection_id"]

    # 2. Confirm consent
    r = client.post(
        f"/bank-sync/connections/{conn_id}/confirm",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "active"
    assert len(data["accounts"]) == 2

    # 3. List connections
    r = client.get("/bank-sync/connections", headers=auth_header)
    assert r.status_code == 200
    conns = r.get_json()
    assert any(c["id"] == conn_id for c in conns)

    # 4. Full sync
    r = client.post(
        f"/bank-sync/connections/{conn_id}/sync",
        json={
            "from_date": "2026-01-01",
            "to_date": "2026-01-07",
        },
        headers=auth_header,
    )
    assert r.status_code == 200
    sync_data = r.get_json()
    assert sync_data["status"] == "success"
    assert sync_data["records_imported"] > 0

    # 5. Check expenses were created
    r = client.get("/expenses", headers=auth_header)
    expenses = r.get_json()
    assert len(expenses) > 0

    # 6. Sync logs
    r = client.get(
        f"/bank-sync/connections/{conn_id}/logs",
        headers=auth_header,
    )
    assert r.status_code == 200
    logs = r.get_json()
    assert len(logs) >= 1
    assert logs[0]["sync_type"] == "full"


def test_refresh_uses_cursor(client, auth_header, app_fixture):
    # Connect + confirm + initial sync
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock"},
        headers=auth_header,
    )
    conn_id = r.get_json()["connection_id"]

    client.post(
        f"/bank-sync/connections/{conn_id}/confirm",
        headers=auth_header,
    )

    client.post(
        f"/bank-sync/connections/{conn_id}/sync",
        json={
            "from_date": "2026-01-01",
            "to_date": "2026-01-07",
        },
        headers=auth_header,
    )

    # Verify cursor was stored
    with app_fixture.app_context():
        conn = db.session.get(BankConnection, conn_id)
        assert conn.sync_cursor is not None
        assert conn.last_sync_at is not None

    # Refresh
    r = client.post(
        f"/bank-sync/connections/{conn_id}/refresh",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["sync_type"] == "refresh"
    assert data["status"] == "success"


def test_duplicate_detection(client, auth_header, app_fixture):
    # Connect + confirm
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock"},
        headers=auth_header,
    )
    conn_id = r.get_json()["connection_id"]

    client.post(
        f"/bank-sync/connections/{conn_id}/confirm",
        headers=auth_header,
    )

    # First sync
    r = client.post(
        f"/bank-sync/connections/{conn_id}/sync",
        json={"from_date": "2026-01-01", "to_date": "2026-01-03"},
        headers=auth_header,
    )
    first_imported = r.get_json()["records_imported"]
    assert first_imported > 0

    # Second sync with same dates — should detect duplicates
    r = client.post(
        f"/bank-sync/connections/{conn_id}/sync",
        json={"from_date": "2026-01-01", "to_date": "2026-01-03"},
        headers=auth_header,
    )
    second_data = r.get_json()
    assert second_data["duplicates_skipped"] > 0


def test_select_account(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock"},
        headers=auth_header,
    )
    conn_id = r.get_json()["connection_id"]

    client.post(
        f"/bank-sync/connections/{conn_id}/confirm",
        headers=auth_header,
    )

    r = client.post(
        f"/bank-sync/connections/{conn_id}/select-account",
        json={"account_id": "mock-current-002"},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["account_id"] == "mock-current-002"
    assert "ICICI" in data["label"]


def test_select_account_invalid(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock"},
        headers=auth_header,
    )
    conn_id = r.get_json()["connection_id"]

    client.post(
        f"/bank-sync/connections/{conn_id}/confirm",
        headers=auth_header,
    )

    r = client.post(
        f"/bank-sync/connections/{conn_id}/select-account",
        json={"account_id": "nonexistent"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_disconnect(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock"},
        headers=auth_header,
    )
    conn_id = r.get_json()["connection_id"]

    r = client.delete(
        f"/bank-sync/connections/{conn_id}",
        headers=auth_header,
    )
    assert r.status_code == 200

    # Verify it's gone
    r = client.get("/bank-sync/connections", headers=auth_header)
    ids = [c["id"] for c in r.get_json()]
    assert conn_id not in ids


def test_disconnect_nonexistent(client, auth_header):
    r = client.delete(
        "/bank-sync/connections/9999",
        headers=auth_header,
    )
    assert r.status_code == 404


def test_sync_before_active_fails(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock"},
        headers=auth_header,
    )
    conn_id = r.get_json()["connection_id"]

    # Try sync without confirming consent
    r = client.post(
        f"/bank-sync/connections/{conn_id}/sync",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "not active" in r.get_json()["error"]


def test_sync_logs_empty(client, auth_header):
    r = client.post(
        "/bank-sync/connect",
        json={"provider": "mock"},
        headers=auth_header,
    )
    conn_id = r.get_json()["connection_id"]

    r = client.get(
        f"/bank-sync/connections/{conn_id}/logs",
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json() == []


def test_connection_not_found(client, auth_header):
    r = client.post(
        "/bank-sync/connections/9999/sync",
        json={},
        headers=auth_header,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Setu AA connector — unit tests (mocked HTTP)
# ---------------------------------------------------------------------------


def test_setu_create_consent_requires_credentials(app_fixture):
    """Without Setu credentials, create_consent should raise."""
    from app.connectors.setu_aa import SetuAAConnector

    c = SetuAAConnector()
    with app_fixture.app_context():
        try:
            c.create_consent(user_id=1, mobile="9876543210")
            assert False, "Should have raised RuntimeError"
        except RuntimeError as exc:
            assert "not configured" in str(exc)
