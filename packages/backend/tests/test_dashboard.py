from datetime import date, timedelta


def test_dashboard_summary_returns_live_data(client, auth_header):
    # Create category for breakdown checks
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]

    # Seed one income and one expense
    r = client.post(
        "/expenses",
        json={
            "amount": 3000,
            "description": "Salary",
            "date": date.today().isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Groceries",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Seed bill
    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 49.99,
            "next_due_date": (date.today() + timedelta(days=3)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert "summary" in payload
    assert payload["summary"]["monthly_income"] >= 3000
    assert payload["summary"]["monthly_expenses"] >= 500
    assert payload["summary"]["net_flow"] >= 2500

    assert isinstance(payload["recent_transactions"], list)
    assert any(t["description"] == "Salary" for t in payload["recent_transactions"])
    assert any(t["type"] == "INCOME" for t in payload["recent_transactions"])

    assert isinstance(payload["upcoming_bills"], list)
    assert len(payload["upcoming_bills"]) >= 1
    assert isinstance(payload["category_breakdown"], list)
    assert any(c["category_name"] == "Food" for c in payload["category_breakdown"])

    # Account fields should exist
    assert "accounts" in payload
    assert isinstance(payload["accounts"], list)
    assert "total_balance" in payload["summary"]
    assert "account_count" in payload["summary"]


def test_dashboard_summary_supports_month_filter(client, auth_header):
    month_a = date.today().replace(day=1)
    month_b = (month_a - timedelta(days=1)).replace(day=1)

    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Current Month Expense",
            "date": month_a.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 999,
            "description": "Previous Month Expense",
            "date": month_b.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        f"/dashboard/summary?month={month_a.strftime('%Y-%m')}", headers=auth_header
    )
    assert r.status_code == 200
    data_a = r.get_json()
    assert data_a["period"]["month"] == month_a.strftime("%Y-%m")
    assert data_a["summary"]["monthly_expenses"] == 200.0

    r = client.get(
        f"/dashboard/summary?month={month_b.strftime('%Y-%m')}", headers=auth_header
    )
    assert r.status_code == 200
    data_b = r.get_json()
    assert data_b["period"]["month"] == month_b.strftime("%Y-%m")
    assert data_b["summary"]["monthly_expenses"] == 999.0


def test_dashboard_accounts_breakdown(client, auth_header):
    # Create two accounts
    r = client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "CHECKING", "balance": 5000.0},
        headers=auth_header,
    )
    assert r.status_code == 201
    checking_id = r.get_json()["id"]

    r = client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "balance": 10000.0},
        headers=auth_header,
    )
    assert r.status_code == 201
    savings_id = r.get_json()["id"]

    # Create expense linked to checking
    r = client.post(
        "/expenses",
        json={
            "amount": 150.0,
            "description": "Restaurant",
            "date": date.today().isoformat(),
            "account_id": checking_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"]["total_balance"] == 15000.0
    assert payload["summary"]["account_count"] == 2
    assert len(payload["accounts"]) == 2

    checking_data = next(a for a in payload["accounts"] if a["id"] == checking_id)
    assert checking_data["expense_count"] == 1
    assert checking_data["month_expenses"] == 150.0

    savings_data = next(a for a in payload["accounts"] if a["id"] == savings_id)
    assert savings_data["expense_count"] == 0
    assert savings_data["month_expenses"] == 0.0
