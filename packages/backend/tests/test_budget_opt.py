def test_auth(client): assert client.get("/budget/optimize").status_code in (401, 422)
def test_optimize_empty(client, auth_header):
    r = client.get("/budget/optimize", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["total_expenses"] == 0
def test_optimize_with_data(client, auth_header):
    client.post("/expenses", json={"amount": 500, "description": "Rent", "expense_type": "EXPENSE"}, headers=auth_header)
    client.post("/expenses", json={"amount": 2000, "description": "Pay", "expense_type": "INCOME"}, headers=auth_header)
    r = client.get("/budget/optimize", headers=auth_header)
    assert r.status_code == 200
    d = r.get_json()
    assert d["total_income"] > 0
    assert isinstance(d["recommendations"], list)
def test_has_categories(client, auth_header):
    client.post("/expenses", json={"amount": 100, "description": "Food", "expense_type": "EXPENSE"}, headers=auth_header)
    r = client.get("/budget/optimize", headers=auth_header)
    assert len(r.get_json()["categories"]) >= 1
