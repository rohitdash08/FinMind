from datetime import date, timedelta


def test_account_crud(client, auth_header):
    """Test create, list, get, update, and soft-delete for accounts."""
    # List should be empty initially
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create account
    payload = {
        "name": "HDFC Savings",
        "account_type": "SAVINGS",
        "currency": "INR",
        "balance": 50000.00,
        "color": "#10b981",
    }
    r = client.post("/accounts", json=payload, headers=auth_header)
    assert r.status_code == 201
    created = r.get_json()
    acct_id = created["id"]
    assert created["name"] == "HDFC Savings"
    assert created["account_type"] == "SAVINGS"
    assert created["balance"] == 50000.00
    assert created["is_active"] is True

    # Creating the first account should also create an "Unassigned" default
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    accounts = r.get_json()
    assert len(accounts) == 2
    names = {a["name"] for a in accounts}
    assert "Unassigned" in names
    assert "HDFC Savings" in names

    # Get single account
    r = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200
    detail = r.get_json()
    assert detail["id"] == acct_id
    assert detail["name"] == "HDFC Savings"

    # Update account
    r = client.put(
        f"/accounts/{acct_id}",
        json={"name": "HDFC Savings Premier", "balance": 55000.00},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "HDFC Savings Premier"
    assert updated["balance"] == 55000.00

    # Soft delete
    r = client.delete(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # After soft-delete, list should only show Unassigned
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    remaining = r.get_json()
    assert len(remaining) == 1
    assert remaining[0]["name"] == "Unassigned"


def test_account_create_requires_name(client, auth_header):
    """Creating an account without a name should return 400."""
    r = client.post("/accounts", json={"account_type": "CHECKING"}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json()["error"].lower()


def test_account_not_found(client, auth_header):
    """Accessing a non-existent account returns 404."""
    r = client.get("/accounts/9999", headers=auth_header)
    assert r.status_code == 404

    r = client.put("/accounts/9999", json={"name": "Test"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/accounts/9999", headers=auth_header)
    assert r.status_code == 404


def test_account_overview(client, auth_header):
    """Test the aggregated overview endpoint."""
    # Create two accounts
    r = client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "CHECKING", "balance": 10000},
        headers=auth_header,
    )
    assert r.status_code == 201
    checking_id = r.get_json()["id"]

    r = client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 25000},
        headers=auth_header,
    )
    assert r.status_code == 201

    # Overview should show total balance across all active accounts
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    overview = r.get_json()
    # 3 accounts: Unassigned (0) + Checking (10000) + Savings (25000)
    assert overview["account_count"] == 3
    assert overview["total_balance"] == 35000.00
    assert len(overview["accounts"]) == 3


def test_expense_account_linking(client, auth_header):
    """Test creating expenses linked to accounts."""
    # Create account
    r = client.post(
        "/accounts",
        json={"name": "Main Account", "account_type": "CHECKING", "balance": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct_id = r.get_json()["id"]

    # Create expense linked to account
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Groceries",
            "date": date.today().isoformat(),
            "account_id": acct_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    expense = r.get_json()
    assert expense["account_id"] == acct_id

    # Create expense without account (backward compatible)
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Random purchase",
            "date": date.today().isoformat(),
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    expense_no_acct = r.get_json()
    assert expense_no_acct["account_id"] is None


def test_expense_account_filter(client, auth_header):
    """Test filtering expenses by account_id."""
    # Create two accounts
    r = client.post(
        "/accounts",
        json={"name": "Account A", "account_type": "CHECKING", "balance": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct_a = r.get_json()["id"]

    r = client.post(
        "/accounts",
        json={"name": "Account B", "account_type": "SAVINGS", "balance": 2000},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct_b = r.get_json()["id"]

    # Create expenses in different accounts
    client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Expense in A",
            "date": date.today().isoformat(),
            "account_id": acct_a,
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 75,
            "description": "Expense in B",
            "date": date.today().isoformat(),
            "account_id": acct_b,
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 25,
            "description": "Unlinked expense",
            "date": date.today().isoformat(),
        },
        headers=auth_header,
    )

    # Filter by account A
    r = client.get(f"/expenses?account_id={acct_a}", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["description"] == "Expense in A"

    # Filter by account B
    r = client.get(f"/expenses?account_id={acct_b}", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["description"] == "Expense in B"

    # No filter — all expenses
    r = client.get("/expenses", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 3


def test_balance_recalculation(client, auth_header):
    """Test that recalculate endpoint recomputes balance from expenses."""
    # Create account
    r = client.post(
        "/accounts",
        json={"name": "Recalc Test", "account_type": "CHECKING", "balance": 0},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct_id = r.get_json()["id"]

    # Add income
    client.post(
        "/expenses",
        json={
            "amount": 1000,
            "description": "Salary",
            "date": date.today().isoformat(),
            "expense_type": "INCOME",
            "account_id": acct_id,
        },
        headers=auth_header,
    )

    # Add expense
    client.post(
        "/expenses",
        json={
            "amount": 300,
            "description": "Rent",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
            "account_id": acct_id,
        },
        headers=auth_header,
    )

    # Recalculate balance
    r = client.post(f"/accounts/{acct_id}/recalculate", headers=auth_header)
    assert r.status_code == 200
    result = r.get_json()
    assert result["balance"] == 700.0  # 1000 income - 300 expense


def test_dashboard_account_filter(client, auth_header):
    """Test that dashboard summary accepts account_id filter."""
    # Create account
    r = client.post(
        "/accounts",
        json={"name": "Dashboard Test", "account_type": "CHECKING", "balance": 0},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct_id = r.get_json()["id"]

    today = date.today()
    ym = today.strftime("%Y-%m")

    # Create expenses: one linked, one not
    client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Linked expense",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "account_id": acct_id,
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Unlinked expense",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    # Without filter — should include both
    r = client.get(f"/dashboard/summary?month={ym}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["monthly_expenses"] >= 700

    # With account filter — should only include linked
    r = client.get(
        f"/dashboard/summary?month={ym}&account_id={acct_id}", headers=auth_header
    )
    assert r.status_code == 200
    data_filtered = r.get_json()
    assert data_filtered["summary"]["monthly_expenses"] == 500.0


def test_dashboard_includes_account_overview(client, auth_header):
    """Test that dashboard summary includes account_overview field."""
    # Create account for overview data
    client.post(
        "/accounts",
        json={"name": "Overview Account", "account_type": "SAVINGS", "balance": 8000},
        headers=auth_header,
    )

    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "account_overview" in data
    overview = data["account_overview"]
    assert overview is not None
    assert overview["total_balance"] >= 8000
    assert overview["account_count"] >= 1


def test_expense_update_account_id(client, auth_header):
    """Test updating an expense to add/change/remove account_id."""
    # Create account
    r = client.post(
        "/accounts",
        json={"name": "Update Test", "account_type": "WALLET", "balance": 100},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct_id = r.get_json()["id"]

    # Create expense without account
    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Test expense",
            "date": date.today().isoformat(),
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    exp_id = r.get_json()["id"]
    assert r.get_json()["account_id"] is None

    # Update to link to account
    r = client.patch(
        f"/expenses/{exp_id}",
        json={"account_id": acct_id},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["account_id"] == acct_id

    # Update to unlink
    r = client.patch(
        f"/expenses/{exp_id}",
        json={"account_id": None},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["account_id"] is None


def test_invalid_account_type_defaults_to_other(client, auth_header):
    """Creating an account with an invalid type should default to OTHER."""
    r = client.post(
        "/accounts",
        json={"name": "Mystery Account", "account_type": "INVALID_TYPE", "balance": 0},
        headers=auth_header,
    )
    assert r.status_code == 201
    created = r.get_json()
    assert created["account_type"] == "OTHER"
