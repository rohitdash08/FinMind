"""Tests for bank sync connector architecture."""


def test_list_providers(client, auth_header):
    r = client.get("/bank/providers", headers=auth_header)
    assert r.status_code == 200
    assert "mock" in r.get_json()["providers"]


def test_connect_mock_bank(client, auth_header):
    r = client.post("/bank/connect", json={
        "provider": "mock",
        "credentials": {"username": "testuser"},
    }, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["provider"] == "mock"
    assert data["status"] == "ACTIVE"


def test_connect_unknown_provider(client, auth_header):
    r = client.post("/bank/connect", json={
        "provider": "nonexistent",
        "credentials": {},
    }, headers=auth_header)
    assert r.status_code == 400


def test_list_connections(client, auth_header):
    client.post("/bank/connect", json={"provider": "mock", "credentials": {}}, headers=auth_header)
    client.post("/bank/connect", json={"provider": "mock", "credentials": {}}, headers=auth_header)

    r = client.get("/bank/connections", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2


def test_list_accounts(client, auth_header):
    r = client.post("/bank/connect", json={"provider": "mock", "credentials": {}}, headers=auth_header)
    conn_id = r.get_json()["id"]

    r = client.get(f"/bank/connections/{conn_id}/accounts", headers=auth_header)
    assert r.status_code == 200
    accounts = r.get_json()
    assert len(accounts) == 2
    assert accounts[0]["name"] == "Mock Checking Account"
    assert accounts[0]["balance"] == 4523.67


def test_sync_transactions(client, auth_header):
    r = client.post("/bank/connect", json={"provider": "mock", "credentials": {}}, headers=auth_header)
    conn_id = r.get_json()["id"]

    r = client.post(f"/bank/connections/{conn_id}/sync", json={
        "account_id": "mock-checking-001",
        "days": 7,
    }, headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["imported"] > 0
    assert data["skipped"] == 0


def test_sync_deduplication(client, auth_header):
    """Second sync should skip already imported transactions."""
    r = client.post("/bank/connect", json={"provider": "mock", "credentials": {}}, headers=auth_header)
    conn_id = r.get_json()["id"]

    # First sync
    r = client.post(f"/bank/connections/{conn_id}/sync", json={
        "account_id": "mock-checking-001",
        "days": 3,
    }, headers=auth_header)
    first_imported = r.get_json()["imported"]

    # Second sync — same period
    r = client.post(f"/bank/connections/{conn_id}/sync", json={
        "account_id": "mock-checking-001",
        "days": 3,
    }, headers=auth_header)
    assert r.get_json()["imported"] == 0
    assert r.get_json()["skipped"] == first_imported


def test_list_imported_transactions(client, auth_header):
    r = client.post("/bank/connect", json={"provider": "mock", "credentials": {}}, headers=auth_header)
    conn_id = r.get_json()["id"]

    client.post(f"/bank/connections/{conn_id}/sync", json={
        "account_id": "mock-checking-001",
        "days": 3,
    }, headers=auth_header)

    r = client.get(f"/bank/connections/{conn_id}/transactions", headers=auth_header)
    assert r.status_code == 200
    transactions = r.get_json()
    assert len(transactions) > 0
    assert "amount" in transactions[0]
    assert "description" in transactions[0]


def test_refresh_connection(client, auth_header):
    r = client.post("/bank/connect", json={"provider": "mock", "credentials": {}}, headers=auth_header)
    conn_id = r.get_json()["id"]

    r = client.post(f"/bank/connections/{conn_id}/refresh", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["status"] == "refreshed"


def test_delete_connection(client, auth_header):
    r = client.post("/bank/connect", json={"provider": "mock", "credentials": {}}, headers=auth_header)
    conn_id = r.get_json()["id"]

    # Sync some transactions first
    client.post(f"/bank/connections/{conn_id}/sync", json={
        "account_id": "mock-checking-001", "days": 3
    }, headers=auth_header)

    r = client.delete(f"/bank/connections/{conn_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/bank/connections", headers=auth_header)
    assert len(r.get_json()) == 0


def test_bank_unauthorized(client):
    r = client.get("/bank/providers")
    assert r.status_code in (401, 422)
