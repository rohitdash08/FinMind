from datetime import date, timedelta


def test_spending_split_requires_auth(client):
    r = client.get("/spending-split")
    assert r.status_code == 401


def test_spending_split_empty_state(client, auth_header):
    r = client.get("/spending-split", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["essential_total"] == 0
    assert payload["discretionary_total"] == 0
    assert payload["total"] == 0
    assert payload["categories"] == []
    assert "period" in payload


def test_spending_split_with_data(client, auth_header):
    today = date.today()

    # Create essential category
    r = client.post("/categories", json={"name": "Groceries"}, headers=auth_header)
    assert r.status_code == 201
    grocery_id = r.get_json()["id"]

    # Create discretionary category
    r = client.post("/categories", json={"name": "Entertainment"}, headers=auth_header)
    assert r.status_code == 201
    ent_id = r.get_json()["id"]

    # Add essential expense
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Weekly groceries",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": grocery_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Add discretionary expense
    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Movie tickets",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": ent_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/spending-split", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["essential_total"] == 200.0
    assert payload["discretionary_total"] == 50.0
    assert payload["total"] == 250.0

    # Check categories are classified
    cats = {c["category_name"]: c for c in payload["categories"]}
    assert cats["Groceries"]["classification"] == "essential"
    assert cats["Entertainment"]["classification"] == "discretionary"


def test_spending_split_ratio_calculation(client, auth_header):
    today = date.today()

    # Create essential category
    r = client.post("/categories", json={"name": "Rent"}, headers=auth_header)
    assert r.status_code == 201
    rent_id = r.get_json()["id"]

    # Create discretionary category
    r = client.post("/categories", json={"name": "Shopping"}, headers=auth_header)
    assert r.status_code == 201
    shop_id = r.get_json()["id"]

    # Add essential expense
    r = client.post(
        "/expenses",
        json={
            "amount": 1000,
            "description": "Monthly rent",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": rent_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Add discretionary expense
    r = client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Clothes",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": shop_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/spending-split", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # Ratio should be essential / discretionary = 1000 / 500 = 2.0
    assert payload["ratio"] == 2.0
    assert payload["essential_pct"] > 0
    assert payload["discretionary_pct"] > 0
    # Percentages should add up to 100
    assert round(payload["essential_pct"] + payload["discretionary_pct"], 1) == 100.0
