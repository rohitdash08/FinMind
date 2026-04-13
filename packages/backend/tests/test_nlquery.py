from datetime import date


def test_nlquery_requires_auth(client):
    r = client.post("/query", json={"question": "how much did I spend?"})
    assert r.status_code == 401


def test_nlquery_how_much_spent(client, auth_header):
    today = date.today()
    # Add an expense
    r = client.post(
        "/expenses",
        json={
            "amount": 42.50,
            "description": "Coffee supplies",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/query",
        json={"question": "how much did I spend this month?"},
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["pattern"] == "total_spending"
    assert "answer" in payload
    assert payload["data"]["total"] == 42.50


def test_nlquery_unknown_query(client, auth_header):
    r = client.post(
        "/query",
        json={"question": "what is the meaning of life?"},
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["pattern"] is None
    assert "couldn't understand" in payload["answer"]


def test_nlquery_empty_question(client, auth_header):
    r = client.post(
        "/query",
        json={"question": ""},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_nlquery_spent_on_category(client, auth_header):
    today = date.today()
    # Create category
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    cat_id = r.get_json()["id"]

    # Add expense in that category
    r = client.post(
        "/expenses",
        json={
            "amount": 75.00,
            "description": "Lunch",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": cat_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/query",
        json={"question": "how much did I spend on food?"},
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["pattern"] == "spent_on_category"
    assert payload["data"]["total"] == 75.00
    assert payload["data"]["category"] == "Food"
