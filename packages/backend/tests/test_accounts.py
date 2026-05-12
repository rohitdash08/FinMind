def test_account_crud(client, auth_header):
    # List empty
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create
    r = client.post(
        "/accounts",
        json={"name": "Main Checking", "account_type": "checking", "currency": "INR", "initial_balance": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct = r.get_json()
    acct_id = acct["id"]
    assert acct["name"] == "Main Checking"
    assert acct["account_type"] == "checking"
    assert acct["currency"] == "INR"
    assert acct["initial_balance"] == 5000.0
    assert acct["is_default"] is True  # first account becomes default
    assert acct["active"] is True

    # List returns one
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Update
    r = client.patch(
        f"/accounts/{acct_id}",
        json={"name": "Updated Checking", "account_type": "savings"},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Updated Checking"
    assert updated["account_type"] == "savings"

    # Soft delete
    r = client.delete(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # List returns empty (soft deleted)
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_account_validation(client, auth_header):
    # Missing name
    r = client.post("/accounts", json={"account_type": "checking"}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]

    # Invalid account_type
    r = client.post(
        "/accounts",
        json={"name": "Bad Type", "account_type": "invalid_type"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "account_type" in r.get_json()["error"]

    # Invalid initial_balance
    r = client.post(
        "/accounts",
        json={"name": "Bad Balance", "initial_balance": "not_a_number"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "initial_balance" in r.get_json()["error"]


def test_account_not_found(client, auth_header):
    r = client.patch("/accounts/9999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/accounts/9999", headers=auth_header)
    assert r.status_code == 404

    r = client.get("/accounts/9999/summary", headers=auth_header)
    assert r.status_code == 404


def test_account_summary_calculation(client, auth_header):
    # Create account
    r = client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "savings", "initial_balance": 10000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct_id = r.get_json()["id"]

    # Add income to this account
    r = client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Salary",
            "expense_type": "INCOME",
            "date": "2026-05-01",
            "account_id": acct_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Add expense to this account
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Groceries",
            "date": "2026-05-02",
            "account_id": acct_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Get summary
    r = client.get(f"/accounts/{acct_id}/summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["balance"] == 10300.0  # 10000 + 500 - 200
    assert data["total_income"] == 500.0
    assert data["total_expenses"] == 200.0
    assert len(data["recent_transactions"]) == 2
    assert data["account"]["id"] == acct_id


def test_multi_account_overview(client, auth_header):
    # Create two accounts
    r = client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "checking", "initial_balance": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct1_id = r.get_json()["id"]

    r = client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "savings", "initial_balance": 20000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct2_id = r.get_json()["id"]

    # Add expense to first account
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Coffee",
            "date": "2026-05-10",
            "account_id": acct1_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Get overview
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_net_worth"] == 24900.0  # 5000 - 100 + 20000
    assert len(data["accounts"]) == 2

    # Verify per-account breakdown
    acct1_data = next(a for a in data["accounts"] if a["account"]["id"] == acct1_id)
    assert acct1_data["balance"] == 4900.0
    assert acct1_data["total_expenses"] == 100.0

    acct2_data = next(a for a in data["accounts"] if a["account"]["id"] == acct2_id)
    assert acct2_data["balance"] == 20000.0


def test_expense_filtering_by_account(client, auth_header):
    # Create two accounts
    r = client.post(
        "/accounts",
        json={"name": "Account A", "initial_balance": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct_a = r.get_json()["id"]

    r = client.post(
        "/accounts",
        json={"name": "Account B", "initial_balance": 2000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct_b = r.get_json()["id"]

    # Add expenses to different accounts
    r = client.post(
        "/expenses",
        json={"amount": 50, "description": "A expense", "date": "2026-05-01", "account_id": acct_a},
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={"amount": 75, "description": "B expense", "date": "2026-05-01", "account_id": acct_b},
        headers=auth_header,
    )
    assert r.status_code == 201

    # Filter by account A
    r = client.get(f"/expenses?account_id={acct_a}", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["description"] == "A expense"
    assert items[0]["account_id"] == acct_a

    # Filter by account B
    r = client.get(f"/expenses?account_id={acct_b}", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["description"] == "B expense"


def test_default_account_logic(client, auth_header):
    # First account automatically becomes default
    r = client.post(
        "/accounts",
        json={"name": "First"},
        headers=auth_header,
    )
    assert r.status_code == 201
    first_id = r.get_json()["id"]
    assert r.get_json()["is_default"] is True

    # Second account is NOT default by default
    r = client.post(
        "/accounts",
        json={"name": "Second"},
        headers=auth_header,
    )
    assert r.status_code == 201
    second_id = r.get_json()["id"]
    assert r.get_json()["is_default"] is False

    # Make second account the default
    r = client.patch(
        f"/accounts/{second_id}",
        json={"is_default": True},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["is_default"] is True

    # First account should no longer be default
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    accounts = r.get_json()
    first = next(a for a in accounts if a["id"] == first_id)
    second = next(a for a in accounts if a["id"] == second_id)
    assert first["is_default"] is False
    assert second["is_default"] is True
