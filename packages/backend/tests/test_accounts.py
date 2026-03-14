from datetime import date, timedelta


def _auth_header_for(client, email, password="password123"):
    """Register + login a user, return auth header."""
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


def _create_account(client, auth_header, **overrides):
    """Helper to create an account with defaults."""
    payload = {
        "name": "My Checking",
        "account_type": "CHECKING",
        "institution": "Bank of Test",
        "currency": "INR",
        "balance": 10000.00,
    }
    payload.update(overrides)
    r = client.post("/accounts", json=payload, headers=auth_header)
    return r


# ---------------------------------------------------------------------------
# CRUD Tests
# ---------------------------------------------------------------------------


def test_create_account(client, auth_header):
    r = _create_account(client, auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "My Checking"
    assert data["account_type"] == "CHECKING"
    assert data["institution"] == "Bank of Test"
    assert data["currency"] == "INR"
    assert data["balance"] == 10000.00
    assert data["is_default"] is False
    assert data["active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_account_missing_name(client, auth_header):
    r = client.post(
        "/accounts",
        json={"account_type": "CHECKING", "balance": 100},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_create_account_invalid_type(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Bad Type", "account_type": "BITCOIN"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "account_type" in r.get_json()["error"]


def test_create_account_invalid_balance(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Bad Balance", "account_type": "SAVINGS", "balance": "abc"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "balance" in r.get_json()["error"]


def test_list_accounts(client, auth_header):
    # Empty initially
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create two accounts
    _create_account(client, auth_header, name="Checking 1")
    _create_account(client, auth_header, name="Savings 1", account_type="SAVINGS")

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    accounts = r.get_json()
    assert len(accounts) == 2
    names = [a["name"] for a in accounts]
    assert "Checking 1" in names
    assert "Savings 1" in names


def test_get_single_account_with_summary(client, auth_header):
    r = _create_account(client, auth_header, name="Test Account", balance=5000)
    acct_id = r.get_json()["id"]

    # Create an expense linked to this account
    client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Coffee",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    r = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "Test Account"
    assert data["balance"] == 5000.0
    assert "summary" in data
    assert "month_expenses" in data["summary"]
    assert "month_income" in data["summary"]
    assert "net_flow" in data["summary"]
    assert "total_transactions" in data["summary"]


def test_get_account_not_found(client, auth_header):
    r = client.get("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_account(client, auth_header):
    r = _create_account(client, auth_header, name="Old Name", balance=1000)
    acct_id = r.get_json()["id"]

    r = client.put(
        f"/accounts/{acct_id}",
        json={"name": "New Name", "balance": 2500.50, "institution": "New Bank"},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["name"] == "New Name"
    assert data["balance"] == 2500.50
    assert data["institution"] == "New Bank"


def test_update_account_invalid_name(client, auth_header):
    r = _create_account(client, auth_header, name="Valid Name")
    acct_id = r.get_json()["id"]

    r = client.put(
        f"/accounts/{acct_id}",
        json={"name": ""},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "name" in r.get_json()["error"]


def test_update_account_not_found(client, auth_header):
    r = client.put(
        "/accounts/99999",
        json={"name": "Nope"},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_soft_delete_account(client, auth_header):
    r = _create_account(client, auth_header, name="To Delete")
    acct_id = r.get_json()["id"]

    # Delete (soft)
    r = client.delete(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "deleted"

    # No longer in list
    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    names = [a["name"] for a in r.get_json()]
    assert "To Delete" not in names

    # Get by ID also returns 404
    r = client.get(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 404

    # Deleting again returns 404
    r = client.delete(f"/accounts/{acct_id}", headers=auth_header)
    assert r.status_code == 404


def test_delete_account_not_found(client, auth_header):
    r = client.delete("/accounts/99999", headers=auth_header)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Default Account Logic
# ---------------------------------------------------------------------------


def test_set_default_account(client, auth_header):
    r1 = _create_account(client, auth_header, name="Account A", is_default=True)
    assert r1.status_code == 201
    assert r1.get_json()["is_default"] is True

    r2 = _create_account(client, auth_header, name="Account B", is_default=True)
    assert r2.status_code == 201
    assert r2.get_json()["is_default"] is True

    # Account A should no longer be default
    r = client.get(f"/accounts/{r1.get_json()['id']}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["is_default"] is False


# ---------------------------------------------------------------------------
# Account Isolation Between Users
# ---------------------------------------------------------------------------


def test_account_isolation_between_users(client, app_fixture):
    header_a = _auth_header_for(client, "user_a@example.com")
    header_b = _auth_header_for(client, "user_b@example.com")

    # User A creates an account
    r = _create_account(client, header_a, name="A Private Account", balance=50000)
    assert r.status_code == 201
    acct_a_id = r.get_json()["id"]

    # User B creates an account
    r = _create_account(client, header_b, name="B Private Account", balance=1000)
    assert r.status_code == 201

    # User B cannot see User A's accounts
    r = client.get("/accounts", headers=header_b)
    assert r.status_code == 200
    names = [a["name"] for a in r.get_json()]
    assert "A Private Account" not in names
    assert "B Private Account" in names

    # User B cannot access User A's account by ID
    r = client.get(f"/accounts/{acct_a_id}", headers=header_b)
    assert r.status_code == 403

    # User B cannot update User A's account
    r = client.put(
        f"/accounts/{acct_a_id}",
        json={"name": "Hacked"},
        headers=header_b,
    )
    assert r.status_code == 403

    # User B cannot delete User A's account
    r = client.delete(f"/accounts/{acct_a_id}", headers=header_b)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Overview / Aggregation Tests
# ---------------------------------------------------------------------------


def test_overview_empty(client, auth_header):
    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_balance"] == 0.0
    assert data["net_worth"] == 0.0
    assert data["accounts_count"] == 0
    assert data["accounts"] == []


def test_overview_aggregation(client, auth_header):
    # Create accounts of various types
    _create_account(
        client, auth_header, name="Checking", account_type="CHECKING", balance=5000
    )
    _create_account(
        client, auth_header, name="Savings", account_type="SAVINGS", balance=20000
    )
    _create_account(
        client,
        auth_header,
        name="Credit Card",
        account_type="CREDIT_CARD",
        balance=1500,
    )

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    # Total balance = 5000 + 20000 + 1500 = 26500
    assert data["total_balance"] == 26500.0
    # Assets = 5000 + 20000 = 25000, Liabilities = 1500
    assert data["total_assets"] == 25000.0
    assert data["total_liabilities"] == 1500.0
    # Net worth = 25000 - 1500 = 23500
    assert data["net_worth"] == 23500.0
    assert data["accounts_count"] == 3
    assert len(data["accounts"]) == 3

    # Check each account breakdown has required fields
    for acct in data["accounts"]:
        assert "id" in acct
        assert "name" in acct
        assert "balance" in acct
        assert "recent_transactions_count" in acct
        assert "month_spending" in acct


def test_overview_month_over_month_change(client, auth_header):
    """Verify month-over-month spending change is calculated."""
    today = date.today()
    first_of_month = today.replace(day=1)
    prev_month = (first_of_month - timedelta(days=1)).replace(day=1)

    # Create an expense in current month
    client.post(
        "/expenses",
        json={
            "amount": 300,
            "description": "Current month expense",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    # Create an expense in previous month
    client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Previous month expense",
            "date": prev_month.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    r = client.get("/accounts/overview", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    # Current month spending = 300, previous = 200, change = 100
    assert data["month_spending"] == 300.0
    assert data["prev_month_spending"] == 200.0
    assert data["month_over_month_change"] == 100.0


def test_overview_isolation_between_users(client, app_fixture):
    """Verify one user's overview doesn't leak another user's data."""
    header_a = _auth_header_for(client, "overview_a@example.com")
    header_b = _auth_header_for(client, "overview_b@example.com")

    _create_account(
        client, header_a, name="A Savings", account_type="SAVINGS", balance=100000
    )
    _create_account(
        client, header_b, name="B Checking", account_type="CHECKING", balance=500
    )

    # User A overview
    r = client.get("/accounts/overview", headers=header_a)
    assert r.status_code == 200
    data_a = r.get_json()
    assert data_a["total_balance"] == 100000.0
    assert data_a["accounts_count"] == 1
    assert data_a["accounts"][0]["name"] == "A Savings"

    # User B overview
    r = client.get("/accounts/overview", headers=header_b)
    assert r.status_code == 200
    data_b = r.get_json()
    assert data_b["total_balance"] == 500.0
    assert data_b["accounts_count"] == 1
    assert data_b["accounts"][0]["name"] == "B Checking"


# ---------------------------------------------------------------------------
# Auth Required
# ---------------------------------------------------------------------------


def test_accounts_require_auth(client):
    """All account endpoints should return 401 without auth."""
    assert client.get("/accounts").status_code == 401
    assert client.post("/accounts", json={}).status_code == 401
    assert client.get("/accounts/1").status_code == 401
    assert client.put("/accounts/1", json={}).status_code == 401
    assert client.delete("/accounts/1").status_code == 401
    assert client.get("/accounts/overview").status_code == 401


# ---------------------------------------------------------------------------
# All Account Types
# ---------------------------------------------------------------------------


def test_all_account_types_accepted(client, auth_header):
    """Verify all valid account types can be created."""
    types = ["CHECKING", "SAVINGS", "CREDIT_CARD", "INVESTMENT", "CASH", "OTHER"]
    for acct_type in types:
        r = _create_account(
            client,
            auth_header,
            name=f"{acct_type} Account",
            account_type=acct_type,
            balance=100,
        )
        assert r.status_code == 201, f"Failed to create {acct_type}: {r.get_json()}"
        assert r.get_json()["account_type"] == acct_type


def test_update_account_type(client, auth_header):
    r = _create_account(client, auth_header, name="Type Change", account_type="CHECKING")
    acct_id = r.get_json()["id"]

    r = client.put(
        f"/accounts/{acct_id}",
        json={"account_type": "SAVINGS"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["account_type"] == "SAVINGS"
