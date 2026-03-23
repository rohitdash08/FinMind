def test_accounts_crud(client, auth_header):
    # Initially empty
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create account
    payload = {
        "name": "Main Checking",
        "account_type": "CHECKING",
        "balance": 5000.50,
        "currency": "USD",
        "institution": "Chase Bank",
    }
    r = client.post("/accounts", json=payload, headers=auth_header)
    assert r.status_code == 201
    account = r.get_json()
    account_id = account["id"]
    assert account["name"] == "Main Checking"
    assert account["account_type"] == "CHECKING"
    assert account["balance"] == 5000.50
    assert account["currency"] == "USD"
    assert account["institution"] == "Chase Bank"
    assert account["active"] is True
    assert "created_at" in account

    # Get single account
    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == account_id

    # List has 1
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Update account
    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "Primary Checking", "balance": 6000},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Primary Checking"
    assert updated["balance"] == 6000.0

    # Delete account (soft-delete by default)
    r = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200

    # Active list is empty (soft-deleted)
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # But it still exists when including inactive
    r = client.get("/accounts?include_inactive=true", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1
    assert r.get_json()[0]["active"] is False


def test_accounts_hard_delete(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Temp Account", "balance": 100},
        headers=auth_header,
    )
    account_id = r.get_json()["id"]

    # Hard delete
    r = client.delete(f"/accounts/{account_id}?hard=true", headers=auth_header)
    assert r.status_code == 200

    # Gone even with include_inactive
    r = client.get("/accounts?include_inactive=true", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 0


def test_accounts_multiple_types(client, auth_header):
    types = ["CHECKING", "SAVINGS", "CREDIT_CARD", "CASH", "INVESTMENT", "OTHER"]
    for t in types:
        r = client.post(
            "/accounts",
            json={"name": f"My {t}", "account_type": t, "balance": 100},
            headers=auth_header,
        )
        assert r.status_code == 201
        assert r.get_json()["account_type"] == t

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 6


def test_accounts_deactivate(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Old Account", "balance": 0},
        headers=auth_header,
    )
    account_id = r.get_json()["id"]

    # Deactivate
    r = client.patch(
        f"/accounts/{account_id}",
        json={"active": False},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["active"] is False

    # Not in default list
    r = client.get("/accounts", headers=auth_header)
    assert len(r.get_json()) == 0

    # Shows with include_inactive
    r = client.get("/accounts?include_inactive=true", headers=auth_header)
    assert len(r.get_json()) == 1


def test_accounts_overview(client, auth_header):
    # Create two accounts
    client.post(
        "/accounts",
        json={"name": "Checking", "balance": 3000, "currency": "USD"},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 7000, "currency": "USD"},
        headers=auth_header,
    )

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["account_count"] == 2
    assert data["total_balance"] == 10000.0
    assert len(data["accounts"]) == 2
    assert "recent_expenses" in data
    assert "upcoming_bills" in data
    # Verify per-currency totals
    assert "totals_by_currency" in data
    assert data["totals_by_currency"]["USD"] == 10000.0


def test_accounts_overview_multi_currency(client, auth_header):
    client.post(
        "/accounts",
        json={"name": "USD Account", "balance": 1000, "currency": "USD"},
        headers=auth_header,
    )
    client.post(
        "/accounts",
        json={"name": "EUR Account", "balance": 2000, "currency": "EUR"},
        headers=auth_header,
    )

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["totals_by_currency"]["USD"] == 1000.0
    assert data["totals_by_currency"]["EUR"] == 2000.0
    assert data["total_balance"] == 3000.0


def test_account_validation(client, auth_header):
    # Missing name
    r = client.post("/accounts", json={"balance": 100}, headers=auth_header)
    assert r.status_code == 400

    # Empty name (whitespace only)
    r = client.post("/accounts", json={"name": "   ", "balance": 100}, headers=auth_header)
    assert r.status_code == 400

    # Invalid account_type
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Name too long
    r = client.post(
        "/accounts",
        json={"name": "A" * 201, "balance": 100},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Not found
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404

    # Update not found
    r = client.patch("/accounts/99999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404

    # Delete not found
    r = client.delete("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_account_update_invalid_balance(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Test", "balance": 100},
        headers=auth_header,
    )
    account_id = r.get_json()["id"]

    r = client.patch(
        f"/accounts/{account_id}",
        json={"balance": "not-a-number"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "invalid balance" in r.get_json()["error"]


def test_account_update_name_too_long(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Test", "balance": 100},
        headers=auth_header,
    )
    account_id = r.get_json()["id"]

    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "X" * 201},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "name too long" in r.get_json()["error"]


def test_account_defaults_to_user_currency(client, auth_header):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/accounts",
        json={"name": "Euro Account", "balance": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "EUR"


def test_account_currency_normalized_uppercase(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Test", "balance": 100, "currency": "usd"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["currency"] == "USD"


def test_account_balance_overflow_rejected(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Overflow", "balance": 99999999999.99},
        headers=auth_header,
    )
    # Balance of 0 since the oversized value is rejected by _parse_amount
    # and falls back to Decimal("0")
    assert r.status_code == 201
    assert r.get_json()["balance"] == 0.0


def test_cross_user_isolation(client, auth_header):
    # Create an account as user 1
    r = client.post(
        "/accounts",
        json={"name": "User1 Account", "balance": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    # Register and login as user 2
    client.post(
        "/auth/register",
        json={"email": "user2@example.com", "password": "password123"},
    )
    r = client.post(
        "/auth/login",
        json={"email": "user2@example.com", "password": "password123"},
    )
    assert r.status_code == 200
    header2 = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    # User 2 should not see user 1's accounts
    r = client.get("/accounts", headers=header2)
    assert r.status_code == 200
    assert r.get_json() == []

    # User 2 cannot access user 1's account directly
    r = client.get(f"/accounts/{account_id}", headers=header2)
    assert r.status_code == 404

    # User 2 cannot update user 1's account
    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "Hacked"},
        headers=header2,
    )
    assert r.status_code == 404

    # User 2 cannot delete user 1's account
    r = client.delete(f"/accounts/{account_id}", headers=header2)
    assert r.status_code == 404


def test_overview_empty(client, auth_header):
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["account_count"] == 0
    assert data["total_balance"] == 0
    assert data["accounts"] == []
    assert data["totals_by_currency"] == {}
