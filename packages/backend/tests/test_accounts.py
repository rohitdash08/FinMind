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

    # Delete account
    r = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200

    # List is empty again
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_accounts_multiple_types(client, auth_header):
    types = ["CHECKING", "SAVINGS", "CREDIT_CARD", "CASH", "INVESTMENT"]
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
    assert len(r.get_json()) == 5


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


def test_account_validation(client, auth_header):
    # Missing name
    r = client.post("/accounts", json={"balance": 100}, headers=auth_header)
    assert r.status_code == 400

    # Invalid account_type
    r = client.post(
        "/accounts",
        json={"name": "Test", "account_type": "INVALID"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Not found
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


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
