"""Tests for multi-account financial overview feature."""
import pytest
from decimal import Decimal


def test_create_account(client, auth_header):
    """Test creating a financial account."""
    response = client.post(
        "/accounts",
        json={
            "name": "Main Checking",
            "account_type": "CHECKING",
            "balance": 5000,
            "currency": "USD",
            "institution": "Chase Bank"
        },
        headers=auth_header
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["account"]["name"] == "Main Checking"
    assert data["account"]["balance"] == 5000
    assert data["account"]["currency"] == "USD"


def test_create_account_missing_name(client, auth_header):
    """Test creating account without name fails."""
    response = client.post(
        "/accounts",
        json={"account_type": "SAVINGS"},
        headers=auth_header
    )
    assert response.status_code == 400


def test_create_account_invalid_type(client, auth_header):
    """Test creating account with invalid type fails."""
    response = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "INVALID_TYPE"},
        headers=auth_header
    )
    assert response.status_code == 400


def test_list_accounts(client, auth_header):
    """Test listing all accounts."""
    # Create multiple accounts
    client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "CHECKING", "balance": 1000},
        headers=auth_header
    )
    client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 5000},
        headers=auth_header
    )
    
    response = client.get("/accounts", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["accounts"]) >= 2


def test_get_single_account(client, auth_header):
    """Test getting a single account by ID."""
    create_resp = client.post(
        "/accounts",
        json={"name": "Credit Card", "account_type": "CREDIT_CARD", "balance": -500},
        headers=auth_header
    )
    account_id = create_resp.get_json()["account"]["id"]
    
    response = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert response.status_code == 200
    assert response.get_json()["account"]["name"] == "Credit Card"


def test_get_nonexistent_account(client, auth_header):
    """Test getting non-existent account returns 404."""
    response = client.get("/accounts/99999", headers=auth_header)
    assert response.status_code == 404


def test_update_account(client, auth_header):
    """Test updating an account."""
    create_resp = client.post(
        "/accounts",
        json={"name": "Old Name", "account_type": "CHECKING", "balance": 100},
        headers=auth_header
    )
    account_id = create_resp.get_json()["account"]["id"]
    
    response = client.put(
        f"/accounts/{account_id}",
        json={"name": "New Name", "balance": 200},
        headers=auth_header
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["account"]["name"] == "New Name"
    assert data["account"]["balance"] == 200


def test_delete_account(client, auth_header):
    """Test soft deleting (deactivating) an account."""
    create_resp = client.post(
        "/accounts",
        json={"name": "To Delete", "account_type": "CASH", "balance": 50},
        headers=auth_header
    )
    account_id = create_resp.get_json()["account"]["id"]
    
    response = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert response.status_code == 200
    
    # Verify it's not in active list
    list_resp = client.get("/accounts", headers=auth_header)
    account_ids = [a["id"] for a in list_resp.get_json()["accounts"]]
    assert account_id not in account_ids


def test_get_overview(client, auth_header):
    """Test getting multi-account overview."""
    # Create multiple accounts with different currencies
    client.post(
        "/accounts",
        json={"name": "USD Checking", "account_type": "CHECKING", "balance": 5000, "currency": "USD"},
        headers=auth_header
    )
    client.post(
        "/accounts",
        json={"name": "USD Savings", "account_type": "SAVINGS", "balance": 10000, "currency": "USD"},
        headers=auth_header
    )
    client.post(
        "/accounts",
        json={"name": "EUR Account", "account_type": "CHECKING", "balance": 3000, "currency": "EUR"},
        headers=auth_header
    )
    
    response = client.get("/accounts/overview", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    # Check structure
    assert "accounts" in data
    assert "summary" in data
    assert "recent_expenses" in data
    assert "upcoming_bills" in data
    
    # Check summary
    assert data["summary"]["total_accounts"] >= 3
    assert "USD" in data["summary"]["totals_by_currency"]
    assert "EUR" in data["summary"]["totals_by_currency"]
    assert data["summary"]["totals_by_currency"]["USD"] == 15000
    assert data["summary"]["totals_by_currency"]["EUR"] == 3000


def test_account_types(client, auth_header):
    """Test all supported account types."""
    types = ["CHECKING", "SAVINGS", "CREDIT_CARD", "CASH", "INVESTMENT", "LOAN", "OTHER"]
    
    for account_type in types:
        response = client.post(
            "/accounts",
            json={"name": f"Test {account_type}", "account_type": account_type, "balance": 100},
            headers=auth_header
        )
        assert response.status_code == 201
        assert response.get_json()["account"]["account_type"] == account_type
