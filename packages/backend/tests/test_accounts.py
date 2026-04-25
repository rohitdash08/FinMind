"""Tests for multi-account financial overview API (bounty #132)."""


def test_accounts_create(client, auth_header):
    """Test creating a financial account."""
    r = client.post(
        "/accounts",
        json={"name": "Main Checking", "account_type": "checking", "balance": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Main Checking"
    assert float(data["balance"]) == 5000.0
    assert data["account_type"] == "checking"
    assert data["is_active"] is True


def test_accounts_create_validation(client, auth_header):
    """Test account creation validation."""
    r = client.post("/accounts", json={"account_type": "checking"}, headers=auth_header)
    assert r.status_code == 400

    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "crypto"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_accounts_list(client, auth_header):
    """Test listing accounts."""
    for atype in ["checking", "savings", "investment"]:
        r = client.post(
            "/accounts",
            json={"name": f"My {atype}", "account_type": atype},
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 3


def test_accounts_overview(client, auth_header):
    """Test multi-account overview."""
    client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "checking", "balance": 3000},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "savings", "balance": 10000},
        headers=auth_header,
    )

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_balance"] == 13000.0
    assert data["accounts_count"] == 2
    assert "checking" in data["by_type"]
    assert "savings" in data["by_type"]


def test_accounts_get_single(client, auth_header):
    """Test getting a single account with transactions."""
    r = client.post(
        "/accounts",
        json={"name": "Test Account", "account_type": "checking", "balance": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == account_id
    assert "recent_transactions" in data


def test_accounts_get_not_found(client, auth_header):
    """Test getting non-existent account returns 404."""
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_accounts_update(client, auth_header):
    """Test updating an account."""
    r = client.post(
        "/accounts",
        json={"name": "Old Name", "account_type": "checking"},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "New Name", "balance": 5000},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "New Name"
    assert float(data["balance"]) == 5000.0


def test_accounts_delete(client, auth_header):
    """Test deactivating an account."""
    r = client.post(
        "/accounts",
        json={"name": "Delete Me", "account_type": "checking"},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    r = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["is_active"] is False


def test_accounts_add_transaction(client, auth_header):
    """Test adding a transaction to an account."""
    r = client.post(
        "/accounts",
        json={"name": "Txn Account", "account_type": "checking", "balance": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    r = client.post(
        f"/accounts/{account_id}/transactions",
        json={"amount": -50, "description": "Coffee", "category": "food"},
        headers=auth_header,
    )
    assert r.status_code == 201
    txn = r.get_json()
    assert float(txn["amount"]) == -50.0

    # Verify balance updated
    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert float(r.get_json()["balance"]) == 950.0


def test_accounts_transaction_validation(client, auth_header):
    """Test transaction validation."""
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "checking"},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    r = client.post(
        f"/accounts/{account_id}/transactions",
        json={"description": "No amount"},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_accounts_list_transactions(client, auth_header):
    """Test listing transactions for an account."""
    r = client.post(
        "/accounts",
        json={"name": "List Txns", "account_type": "checking", "balance": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    for i in range(3):
        r = client.post(
            f"/accounts/{account_id}/transactions",
            json={"amount": -10 * (i + 1), "description": f"Txn {i}"},
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get(f"/accounts/{account_id}/transactions", headers=auth_header)
    assert r.status_code == 200
    txns = r.get_json()
    assert len(txns) == 3
