from datetime import date, timedelta


def test_budget_suggest_requires_auth(client):
    r = client.get("/budget-suggest")
    assert r.status_code == 401


def test_budget_suggest_empty_state(client, auth_header):
    r = client.get("/budget-suggest", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["suggestions"] == []
    assert payload["monthly_income"] == 0.0
    assert payload["savings_target"] >= 0
    assert "budget_rule" in payload
    assert "period" in payload


def test_budget_suggest_with_data(client, auth_header):
    today = date.today()
    # Create a category
    r = client.post("/categories", json={"name": "Groceries"}, headers=auth_header)
    assert r.status_code == 201
    cat_id = r.get_json()["id"]

    # Add expenses over the last 90 days
    for i in range(3):
        expense_date = (today - timedelta(days=i * 30)).isoformat()
        r = client.post(
            "/expenses",
            json={
                "amount": 300,
                "description": f"Grocery run {i}",
                "date": expense_date,
                "expense_type": "EXPENSE",
                "category_id": cat_id,
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    # Add some income
    r = client.post(
        "/expenses",
        json={
            "amount": 5000,
            "description": "Salary",
            "date": today.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/budget-suggest", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert len(payload["suggestions"]) >= 1
    assert payload["monthly_income"] > 0
    assert payload["savings_target"] > 0

    # Check budget rule follows 50/30/20
    rule = payload["budget_rule"]
    assert "needs" in rule
    assert "wants" in rule
    assert "savings" in rule

    # Check suggestions have expected fields
    suggestion = payload["suggestions"][0]
    assert "category_id" in suggestion
    assert "category_name" in suggestion
    assert "monthly_average" in suggestion
    assert "suggested_budget" in suggestion
    # Suggested budget should be higher than average (10% buffer)
    assert suggestion["suggested_budget"] >= suggestion["monthly_average"]
