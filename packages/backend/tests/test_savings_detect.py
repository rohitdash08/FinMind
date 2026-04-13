def test_auth(client): assert client.get("/savings-opportunities").status_code in (401, 422)
def test_empty(client, auth_header):
    r = client.get("/savings-opportunities", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["opportunity_count"] == 0
def test_with_spending(client, auth_header):
    for i in range(5):
        client.post("/expenses", json={"amount": 200, "description": f"Big spend {i}", "expense_type": "EXPENSE"}, headers=auth_header)
    r = client.get("/savings-opportunities", headers=auth_header)
    assert r.status_code == 200
def test_small_purchases(client, auth_header):
    for i in range(15):
        client.post("/expenses", json={"amount": 5, "description": f"Coffee {i}", "expense_type": "EXPENSE"}, headers=auth_header)
    r = client.get("/savings-opportunities", headers=auth_header)
    opps = r.get_json()["opportunities"]
    small = [o for o in opps if o["type"] == "small_purchases"]
    assert len(small) >= 1
