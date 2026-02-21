"""Tests for multi-account feature."""
import pytest


def test_create_account(client, auth_header):
    """Test creating a financial account."""
    response = client.post("/accounts",
        json={
            "name": "Main Checking",
            "account_type": "CHECKING",
            "balance": 5000,
            "currency": "USD",
            "institution": "Chase"
        },
        headers=auth_header
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["account"]["name"] == "Main Checking"
    assert float(data["account"]["balance"]) == 5000


def test_create_account_invalid_type(client, auth_header):
    """Test creating account with invalid type fails."""
    response = client.post("/accounts",
        json={"name": "Test", "account_type": "INVALID"},
        headers=auth_header
    )
    assert response.status_code == 400


def test_list_accounts(client, auth_header):
    """Test listing accounts."""
    client.post("/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 10000},
        headers=auth_header
    )
    
    response = client.get("/accounts", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["accounts"]) >= 1


def test_get_single_account(client, auth_header):
    """Test getting a single account."""
    create_resp = client.post("/accounts",
        json={"name": "Credit Card", "account_type": "CREDIT_CARD", "balance": -500},
        headers=auth_header
    )
    account_id = create_resp.get_json()["account"]["id"]
    
    response = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert response.status_code == 200
    assert response.get_json()["account"]["name"] == "Credit Card"


def test_update_account(client, auth_header):
    """Test updating an account."""
    create_resp = client.post("/accounts",
        json={"name": "Old Name", "account_type": "CHECKING", "balance": 100},
        headers=auth_header
    )
    account_id = create_resp.get_json()["account"]["id"]
    
    response = client.put(f"/accounts/{account_id}",
        json={"name": "New Name", "balance": 200},
        headers=auth_header
    )
    assert response.status_code == 200
    assert response.get_json()["account"]["name"] == "New Name"


def test_delete_account(client, auth_header):
    """Test deleting (deactivating) an account."""
    create_resp = client.post("/accounts",
        json={"name": "To Delete", "account_type": "CASH", "balance": 50},
        headers=auth_header
    )
    account_id = create_resp.get_json()["account"]["id"]
    
    response = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert response.status_code == 200
    
    # Verify it's deactivated (not in list)
    list_resp = client.get("/accounts", headers=auth_header)
    account_ids = [a["id"] for a in list_resp.get_json()["accounts"]]
    assert account_id not in account_ids


def test_get_overview(client, auth_header):
    """Test getting multi-account overview."""
    # Create multiple accounts
    client.post("/accounts",
        json={"name": "Checking", "account_type": "CHECKING", "balance": 5000, "currency": "USD"},
        headers=auth_header
    )
    client.post("/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 10000, "currency": "USD"},
        headers=auth_header
    )
    
    response = client.get("/accounts/overview", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    assert data["overview"]["total_accounts"] >= 2
    assert data["overview"]["total_balance"] >= 15000
    assert "by_type" in data["overview"]
    assert "by_currency" in data["overview"]


def test_account_not_found(client, auth_header):
    """Test getting non-existent account."""
    response = client.get("/accounts/99999", headers=auth_header)
    assert response.status_code == 404
