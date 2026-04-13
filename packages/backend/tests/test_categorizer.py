from app.services.categorizer import suggest_category, bulk_categorize
def test_auth(client): assert client.post("/categorize/suggest").status_code in (401, 422)
def test_suggest_grocery(client, auth_header):
    r = client.post("/categorize/suggest", json={"description": "Weekly grocery shopping"}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["suggested_category"] == "Groceries"
def test_suggest_unknown(client, auth_header):
    r = client.post("/categorize/suggest", json={"description": "xyzabc"}, headers=auth_header)
    assert r.get_json()["suggested_category"] is None
def test_bulk_empty(client, auth_header):
    r = client.post("/categorize/bulk", headers=auth_header)
    assert r.status_code == 200
def test_keywords(client, auth_header):
    r = client.get("/categorize/keywords", headers=auth_header)
    assert r.status_code == 200
    assert "Groceries" in r.get_json()["categories"]
def test_unit_suggest():
    assert suggest_category("uber ride")["suggested_category"] == "Transport"
    assert suggest_category("netflix sub")["suggested_category"] == "Entertainment"
    assert suggest_category("salary deposit")["suggested_category"] == "Income"
