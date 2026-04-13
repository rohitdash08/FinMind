def test_accounts_crud(client, auth_header):
    # List empty
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create first account (auto-default)
    r = client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "CHECKING", "balance": 1000.50},
        headers=auth_header,
    )
    assert r.status_code == 201
    acct = r.get_json()
    assert acct["name"] == "Checking"
    assert acct["account_type"] == "CHECKING"
    assert acct["balance"] == 1000.50
    assert acct["is_default"] is True
    acct_id = acct["id"]

    # Create second account
    r = client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    savings = r.get_json()
    assert savings["is_default"] is False

    # List returns both
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2

    # Get single account
    r = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["name"] == "Checking"

    # Update account
    r = client.patch(
        f"/accounts/{acct_id}",
        json={"name": "Main Checking", "balance": 1200},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Main Checking"
    assert r.get_json()["balance"] == 1200.0

    # Soft delete
    r = client.delete(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200

    # List returns only savings (now promoted to default)
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["name"] == "Savings"
    assert items[0]["is_default"] is True

    # Deleted account returns 404
    r = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 404


def test_account_validation(client, auth_header):
    r = client.post("/accounts", json={"account_type": "CHECKING"}, headers=auth_header)
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]

    r = client.post("/accounts", json={"name": "Bad", "account_type": "INVALID"}, headers=auth_header)
    assert r.status_code == 400
    assert "account_type" in r.get_json()["error"]

    r = client.post("/accounts", json={"name": "Bad", "balance": "not-a-number"}, headers=auth_header)
    assert r.status_code == 400
    assert "balance" in r.get_json()["error"]


def test_set_default_account(client, auth_header):
    r = client.post("/accounts", json={"name": "A1", "account_type": "CHECKING"}, headers=auth_header)
    assert r.status_code == 201
    a1_id = r.get_json()["id"]

    r = client.post("/accounts", json={"name": "A2", "account_type": "SAVINGS", "is_default": True}, headers=auth_header)
    assert r.status_code == 201
    assert r.get_json()["is_default"] is True

    r = client.get(f"/accounts/{a1_id}", headers=auth_header)
    assert r.get_json()["is_default"] is False


def test_account_summary(client, auth_header):
    r = client.post("/accounts", json={"name": "Test", "account_type": "CHECKING", "balance": 500}, headers=auth_header)
    acct_id = r.get_json()["id"]

    r = client.post("/expenses", json={"amount": 50.0, "description": "Groceries", "date": "2026-04-10", "account_id": acct_id}, headers=auth_header)
    assert r.status_code == 201
    assert r.get_json()["account_id"] == acct_id

    r = client.get(f"/accounts/{acct_id}/summary?month=2026-04", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["account"]["id"] == acct_id
    assert data["summary"]["monthly_expenses"] == 50.0
    assert data["summary"]["net_flow"] == -50.0


def test_dashboard_overview(client, auth_header):
    r = client.post("/accounts", json={"name": "Checking", "balance": 1000}, headers=auth_header)
    checking_id = r.get_json()["id"]

    r = client.post("/accounts", json={"name": "Savings", "account_type": "SAVINGS", "balance": 5000}, headers=auth_header)
    savings_id = r.get_json()["id"]

    client.post("/expenses", json={"amount": 100, "description": "Expense 1", "date": "2026-04-05", "account_id": checking_id}, headers=auth_header)
    client.post("/expenses", json={"amount": 200, "description": "Expense 2", "date": "2026-04-06", "account_id": savings_id}, headers=auth_header)

    r = client.get("/dashboard/overview?month=2026-04", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_balance"] == 6000.0
    assert data["accounts_count"] == 2
    assert data["aggregate"]["monthly_expenses"] == 300.0
    assert data["aggregate"]["net_flow"] == -300.0
    assert len(data["accounts"]) == 2


def test_dashboard_summary_with_account_filter(client, auth_header):
    r = client.post("/accounts", json={"name": "Filtered", "balance": 100}, headers=auth_header)
    acct_id = r.get_json()["id"]

    client.post("/expenses", json={"amount": 30, "description": "Linked", "date": "2026-04-01", "account_id": acct_id}, headers=auth_header)
    client.post("/expenses", json={"amount": 70, "description": "Unlinked", "date": "2026-04-01"}, headers=auth_header)

    r = client.get("/dashboard/summary?month=2026-04", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["summary"]["monthly_expenses"] == 100.0

    r = client.get(f"/dashboard/summary?month=2026-04&account_id={acct_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["monthly_expenses"] == 30.0
    assert data["account_id"] == acct_id


def test_expenses_filter_by_account(client, auth_header):
    r = client.post("/accounts", json={"name": "Filter Test"}, headers=auth_header)
    acct_id = r.get_json()["id"]

    client.post("/expenses", json={"amount": 10, "description": "With account", "date": "2026-04-01", "account_id": acct_id}, headers=auth_header)
    client.post("/expenses", json={"amount": 20, "description": "No account", "date": "2026-04-01"}, headers=auth_header)

    r = client.get(f"/expenses?account_id={acct_id}", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["account_id"] == acct_id

    r = client.get("/expenses", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 2


def test_account_not_found(client, auth_header):
    r = client.get("/accounts/9999", headers=auth_header)
    assert r.status_code == 404
    r = client.patch("/accounts/9999", json={"name": "X"}, headers=auth_header)
    assert r.status_code == 404
    r = client.delete("/accounts/9999", headers=auth_header)
    assert r.status_code == 404
    r = client.get("/accounts/9999/summary", headers=auth_header)
    assert r.status_code == 404
