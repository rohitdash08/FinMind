from datetime import date, timedelta


def test_monthly_review_requires_auth(client):
    r = client.get("/review/monthly")
    assert r.status_code in (401, 422)


def test_monthly_review_empty(client, auth_header):
    r = client.get("/review/monthly?month=2025-01", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["month"] == "2025-01"
    assert data["income"] == 0
    assert data["expenses"] == 0
    assert data["savings_rate"] == 0
    assert data["top_categories"] == []


def test_monthly_review_with_data(client, auth_header):
    today = date.today()
    ym = today.strftime("%Y-%m")

    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]

    client.post(
        "/expenses",
        json={
            "amount": 5000,
            "description": "Salary",
            "date": today.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 800,
            "description": "Groceries",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
        headers=auth_header,
    )

    r = client.get(f"/review/monthly?month={ym}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["income"] >= 5000
    assert data["expenses"] >= 800
    assert data["savings_rate"] > 0
    assert len(data["top_categories"]) >= 1
    assert "vs_previous_month" in data
    assert "highlights" in data


def test_monthly_review_default_month(client, auth_header):
    r = client.get("/review/monthly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["month"] == date.today().strftime("%Y-%m")
