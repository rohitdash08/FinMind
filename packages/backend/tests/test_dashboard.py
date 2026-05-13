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


def test_dashboard_summary_groups_by_financial_account(client, auth_header):
    r = client.post(
        "/accounts",
        json={"name": "Checking", "account_type": "CHECKING", "opening_balance": 1000},
        headers=auth_header,
    )
    assert r.status_code == 201
    checking_id = r.get_json()["id"]

    r = client.post(
        "/accounts",
        json={"name": "Savings", "account_type": "SAVINGS", "opening_balance": 5000},
        headers=auth_header,
    )
    assert r.status_code == 201
    savings_id = r.get_json()["id"]

    today = date.today()
    for account_id, amount, description, expense_type in [
        (checking_id, 2500, "Salary", "INCOME"),
        (checking_id, 400, "Rent", "EXPENSE"),
        (savings_id, 100, "Interest", "INCOME"),
    ]:
        r = client.post(
            "/expenses",
            json={
                "account_id": account_id,
                "amount": amount,
                "description": description,
                "date": today.isoformat(),
                "expense_type": expense_type,
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get(
        f"/dashboard/summary?month={today.strftime('%Y-%m')}", headers=auth_header
    )
    assert r.status_code == 200
    payload = r.get_json()
    accounts = {item["name"]: item for item in payload["account_overview"]}
    assert accounts["Checking"]["monthly_income"] == 2500
    assert accounts["Checking"]["monthly_expenses"] == 400
    assert accounts["Checking"]["projected_balance"] == 3100
    assert accounts["Savings"]["monthly_income"] == 100
    assert accounts["Savings"]["projected_balance"] == 5100
    assert any(t["account_id"] == checking_id for t in payload["recent_transactions"])
