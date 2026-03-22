"""Tests for multi-account financial overview."""

from datetime import date


def test_create_account(client, auth_header):
    """Create a new financial account."""
    r = client.post(
        "/accounts",
        json={
            "name": "My Savings",
            "account_type": "SAVINGS",
            "balance": 5000.00,
            "currency": "INR",
            "institution": "SBI",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "My Savings"
    assert data["account_type"] == "SAVINGS"
    assert data["balance"] == 5000.00
    assert data["institution"] == "SBI"
    assert data["active"] is True


def test_create_account_requires_name(client, auth_header):
    """Account creation fails without a name."""
    r = client.post("/accounts", json={"balance": 100}, headers=auth_header)
    assert r.status_code == 400


def test_list_accounts(client, auth_header):
    """List all active accounts."""
    client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "CHECKING"},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Credit Card", "account_type": "CREDIT_CARD"},
        headers=auth_header,
    )
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 2
    assert data[0]["name"] == "Checking"
    assert data[1]["name"] == "Credit Card"


def test_get_single_account(client, auth_header):
    """Get a single account by ID."""
    r = client.post(
        "/accounts",
        json={"name": "Investment", "account_type": "INVESTMENT", "balance": 10000},
        headers=auth_header,
    )
    acct_id = r.get_json()["id"]
    r = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Investment"


def test_get_nonexistent_account(client, auth_header):
    """Returns 404 for non-existent account."""
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_account(client, auth_header):
    """Update account details."""
    r = client.post(
        "/accounts",
        json={"name": "Old Name"},
        headers=auth_header,
    )
    acct_id = r.get_json()["id"]
    r = client.put(
        f"/accounts/{acct_id}",
        json={"name": "New Name", "balance": 999},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "New Name"
    assert r.get_json()["balance"] == 999.0


def test_delete_account(client, auth_header):
    """Soft-delete sets account to inactive."""
    r = client.post(
        "/accounts",
        json={"name": "To Delete"},
        headers=auth_header,
    )
    acct_id = r.get_json()["id"]
    r = client.delete(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200

    # Should not appear in list
    r = client.get("/accounts", headers=auth_header)
    names = [a["name"] for a in r.get_json()]
    assert "To Delete" not in names


def test_overview_empty(client, auth_header):
    """Overview works with no accounts."""
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_accounts"] == 0
    assert data["total_balance"] == 0.0
    assert data["accounts"] == []


def test_overview_with_accounts(client, auth_header):
    """Overview shows aggregated balances."""
    client.post(
        "/accounts",
        json={"name": "Savings", "balance": 3000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Checking", "balance": 2000},
        headers=auth_header,
    )
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_accounts"] == 2
    assert data["total_balance"] == 5000.0
    assert len(data["accounts"]) == 2


def test_overview_requires_auth(client):
    """Overview endpoint requires authentication."""
    r = client.get("/accounts/overview")
    assert r.status_code == 401
