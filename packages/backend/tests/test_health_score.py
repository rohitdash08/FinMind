def test_auth(client): assert client.get("/health-score").status_code in (401, 422)
def test_score_empty(client, auth_header):
    r = client.get("/health-score", headers=auth_header)
    assert r.status_code == 200
    d = r.get_json()
    assert 0 <= d["score"] <= 100
    assert d["grade"] in ("Excellent", "Good", "Fair", "Needs Improvement")
def test_score_with_data(client, auth_header):
    client.post("/expenses", json={"amount": 5000, "description": "Salary", "expense_type": "INCOME"}, headers=auth_header)
    client.post("/expenses", json={"amount": 1000, "description": "Rent", "expense_type": "EXPENSE"}, headers=auth_header)
    r = client.get("/health-score", headers=auth_header)
    d = r.get_json()
    assert d["score"] > 50
    assert len(d["factors"]) >= 2
    assert isinstance(d["tips"], list)
def test_has_factors(client, auth_header):
    r = client.get("/health-score", headers=auth_header)
    factors = r.get_json()["factors"]
    names = [f["name"] for f in factors]
    assert "Savings Rate" in names
