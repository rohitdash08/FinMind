from datetime import date


def test_accounts_crud(client, auth_header):
    # List should be empty
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create account
    r = client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "CHECKING", "currency": "USD", "balance": 5000.0},
        headers=auth_header,
    )
    assert r.status_code == 201
    created = r.get_json()
    assert created["name"] == "Checking"
    assert created["account_type"] == "CHECKING"
    assert created["balance"] == 5000.0
    assert created["currency"] == "USD"
    assert created["is_active"] is True
    account_id = created["id"]

    # Create second account
    r = client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 10000.0},
        headers=auth_header,
    )
    assert r.status_code == 201

    # List
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 2

    # Get single
    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert detail["name"] == "Checking"
    assert "expense_count" in detail
    assert "month_expenses" in detail
    assert "month_income" in detail

    # Update
    r = client.patch(
        f"/accounts/{account_id}",
        json={"name": "Primary Checking", "balance": 5500.0},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Primary Checking"
    assert updated["balance"] == 5500.0

    # Delete
    r = client.delete(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200

    # List should have 1 remaining
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1


def test_account_get_with_expenses(client, auth_header):
    # Create account
    r = client.post(
        "/accounts",
        json={"name": "Test Account", "account_type": "CHECKING", "balance": 1000.0},
        headers=auth_header,
    )
    assert r.status_code == 201
    account_id = r.get_json()["id"]

    # Create expense linked to account
    r = client.post(
        "/expenses",
        json={
            "amount": 50.0,
            "description": "Groceries",
            "date": date.today().isoformat(),
            "account_id": account_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Get account should show expense info
    r = client.get(f"/accounts/{account_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert detail["expense_count"] == 1
    assert detail["month_expenses"] == 50.0


def test_account_create_validation(client, auth_header):
    # Missing name
    r = client.post("/accounts", json={"account_type": "CHECKING"}, headers=auth_header)
    assert r.status_code == 400

    # Invalid account_type
    r = client.post("/accounts", json={"name": "X", "account_type": "INVALID"}, headers=auth_header)
    assert r.status_code == 400


def test_account_not_found(client, auth_header):
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404

    r = client.patch("/accounts/99999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_account_create_defaults(client, auth_header):
    # Should use default account_type and balance
    r = client.post(
        "/accounts",
        json={"name": "Cash Wallet"},
        headers=auth_header,
    )
    assert r.status_code == 201
    created = r.get_json()
    assert created["account_type"] == "CHECKING"
    assert created["balance"] == 0.0
