from datetime import date, timedelta
def _add(c, h, amt, desc, typ="EXPENSE"):
    c.post("/expenses", json={"amount": amt, "description": desc, "expense_type": typ}, headers=h)

def test_auth(client): assert client.post("/scenarios/simulate").status_code in (401, 422)

def test_simulate_empty(client, auth_header):
    r = client.post("/scenarios/simulate", json={"months": 3}, headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()["projection"]) == 3

def test_simulate_with_data(client, auth_header):
    _add(client, auth_header, 1000, "Salary", "INCOME")
    _add(client, auth_header, 500, "Rent")
    r = client.post("/scenarios/simulate", json={"months": 6, "income_change_pct": 10}, headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["adjustments"]["income_change_pct"] == 10

def test_one_time_expense(client, auth_header):
    r = client.post("/scenarios/simulate", json={"months": 3, "one_time_expense": 5000}, headers=auth_header)
    assert r.status_code == 200
    p = r.get_json()["projection"]
    assert p[0]["expenses"] >= 5000

def test_max_months(client, auth_header):
    r = client.post("/scenarios/simulate", json={"months": 99}, headers=auth_header)
    assert len(r.get_json()["projection"]) == 24
