from datetime import date, timedelta


def test_monthly_review_returns_aggregates(client, auth_header):
    today = date.today()
    ym = today.strftime("%Y-%m")

    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]

    r = client.post("/categories", json={"name": "Transport"}, headers=auth_header)
    assert r.status_code == 201
    transport_id = r.get_json()["id"]

    r = client.post(
        "/expenses",
        json={
            "amount": 3000,
            "description": "Salary",
            "date": today.isoformat(),
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
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Gas",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": transport_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(f"/review/monthly-review?month={ym}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["period"] == ym
    assert "previous_period" in payload
    assert payload["current"]["total_income"] >= 3000
    assert payload["current"]["total_expenses"] >= 700
    assert len(payload["current"]["categories"]) >= 1
    assert isinstance(payload["reviews"], list)
    assert isinstance(payload["recommendations"], list)


def test_monthly_review_empty_month(client, auth_header):
    r = client.get("/review/monthly-review?month=2020-01", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["current"]["total_income"] == 0
    assert payload["current"]["total_expenses"] == 0
    assert payload["current"]["transaction_count"] == 0


def test_monthly_review_invalid_month(client, auth_header):
    r = client.get("/review/monthly-review?month=bad-date", headers=auth_header)
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_monthly_review_generates_reviews_and_recommendations(client, auth_header):
    today = date.today()
    ym = today.strftime("%Y-%m")

    r = client.post(
        "/expenses",
        json={
            "amount": 5000,
            "description": "High expense month",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(f"/review/monthly-review?month={ym}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    has_negative_flow = any(rv["type"] == "negative_flow" for rv in payload["reviews"])
    has_recommendations = len(payload["recommendations"]) > 0
    assert has_negative_flow or has_recommendations
