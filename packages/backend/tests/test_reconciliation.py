def test_auth(client): assert client.get("/reconciliation/check").status_code in (401, 422)
def test_healthy(client, auth_header):
    r = client.get("/reconciliation/check", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["healthy"] is True
def test_with_data(client, auth_header):
    client.post("/expenses", json={"amount": 100, "description": "Test", "expense_type": "EXPENSE"}, headers=auth_header)
    r = client.get("/reconciliation/check", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["summary"]["total_records"] >= 1
def test_duplicate_detection(client, auth_header):
    for _ in range(3):
        client.post("/expenses", json={"amount": 99.99, "description": "Same thing", "expense_type": "EXPENSE"}, headers=auth_header)
    r = client.get("/reconciliation/check", headers=auth_header)
    issues = r.get_json()["issues"]
    dupe_issues = [i for i in issues if i["type"] == "duplicate"]
    assert len(dupe_issues) >= 1
