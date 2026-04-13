from datetime import date, timedelta


def test_spending_insights_requires_auth(client):
    r = client.get("/spending-insights")
    assert r.status_code == 401


def test_spending_insights_empty_state(client, auth_header):
    r = client.get("/spending-insights", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_spent"] == 0
    assert payload["daily_average"] == 0
    assert payload["insights"] == []
    assert payload["categories"] == []
    assert "period" in payload


def test_spending_insights_with_data(client, auth_header):
    today = date.today()
    # Create a category
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    cat_id = r.get_json()["id"]

    # Add current period expenses
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Groceries",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": cat_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Add previous period expense (smaller, to trigger spike)
    prev_date = (today - timedelta(days=35)).isoformat()
    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Old groceries",
            "date": prev_date,
            "expense_type": "EXPENSE",
            "category_id": cat_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/spending-insights?days=30", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_spent"] == 200.0
    assert len(payload["categories"]) >= 1
    assert payload["categories"][0]["category_name"] == "Food"
    # Should detect a spike (200 vs 50 = 300% increase)
    spike_insights = [i for i in payload["insights"] if i["type"] == "spike"]
    assert len(spike_insights) >= 1
    assert "explanation" in spike_insights[0]


def test_spending_insights_daily_average(client, auth_header):
    today = date.today()
    # Add two expenses in the current period
    for i in range(3):
        r = client.post(
            "/expenses",
            json={
                "amount": 30,
                "description": f"Expense {i}",
                "date": (today - timedelta(days=i)).isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get("/spending-insights?days=30", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_spent"] == 90.0
    assert payload["daily_average"] == 3.0  # 90 / 30
