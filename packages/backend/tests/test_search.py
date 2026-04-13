"""Tests for advanced search."""


def _add_expense(client, auth_header, amount, desc, expense_type="EXPENSE"):
    r = client.post("/expenses", json={"amount": amount, "description": desc, "expense_type": expense_type}, headers=auth_header)
    assert r.status_code == 201


# 1. Auth required
def test_search_requires_auth(client):
    r = client.get("/search")
    assert r.status_code in (401, 422)


# 2. Text search in notes
def test_search_by_text(client, auth_header):
    _add_expense(client, auth_header, 50, "Weekly grocery shopping")
    _add_expense(client, auth_header, 30, "Gas station fill up")
    r = client.get("/search?q=grocery", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] >= 1
    assert any("grocery" in e["description"].lower() for e in data["expenses"])


# 3. Amount range filter
def test_search_by_amount_range(client, auth_header):
    _add_expense(client, auth_header, 500, "Big purchase")
    _add_expense(client, auth_header, 10, "Small item")
    r = client.get("/search?min_amount=100&max_amount=1000", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert all(e["amount"] >= 100 for e in data["expenses"])


# 4. Filter by expense type
def test_search_by_type(client, auth_header):
    _add_expense(client, auth_header, 2000, "Salary", "INCOME")
    _add_expense(client, auth_header, 50, "Lunch", "EXPENSE")
    r = client.get("/search?expense_type=INCOME", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert all(e["expense_type"] == "INCOME" for e in data["expenses"])


# 5. Search expenses only
def test_search_source_expenses(client, auth_header):
    _add_expense(client, auth_header, 100, "Test")
    r = client.get("/search?source=expenses", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "expenses" in data
    assert data["bills"] == []


# 6. Empty search returns all
def test_search_empty_query(client, auth_header):
    _add_expense(client, auth_header, 25, "Item A")
    _add_expense(client, auth_header, 75, "Item B")
    r = client.get("/search", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] >= 2


# 7. Invalid amount returns 400
def test_invalid_amount(client, auth_header):
    r = client.get("/search?min_amount=abc", headers=auth_header)
    assert r.status_code == 400


# 8. Combined filters
def test_combined_filters(client, auth_header):
    _add_expense(client, auth_header, 200, "Grocery haul", "EXPENSE")
    _add_expense(client, auth_header, 15, "Grocery snack", "EXPENSE")
    r = client.get("/search?q=grocery&min_amount=100", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert all(e["amount"] >= 100 and "grocery" in e["description"].lower() for e in data["expenses"])
