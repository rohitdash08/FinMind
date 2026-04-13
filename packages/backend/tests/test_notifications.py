def test_auth(client): assert client.get("/notifications").status_code in (401, 422)
def test_create(client, auth_header):
    r = client.post("/notifications", json={"message": "Bill due", "priority": "high", "group": "bills"}, headers=auth_header)
    assert r.status_code == 201
    assert r.get_json()["priority"] == "high"
def test_list(client, auth_header):
    client.post("/notifications", json={"message": "Test", "priority": "low"}, headers=auth_header)
    r = client.get("/notifications", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) >= 1
def test_grouped(client, auth_header):
    client.post("/notifications", json={"message": "A", "group": "bills"}, headers=auth_header)
    client.post("/notifications", json={"message": "B", "group": "alerts"}, headers=auth_header)
    r = client.get("/notifications/grouped", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["group_count"] >= 1
def test_filter_priority(client, auth_header):
    client.post("/notifications", json={"message": "Urgent", "priority": "critical"}, headers=auth_header)
    r = client.get("/notifications?priority=critical", headers=auth_header)
    assert all(n["priority"] == "critical" for n in r.get_json())
