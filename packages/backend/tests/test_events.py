def test_auth(client): assert client.get("/events/stream").status_code in (401, 422)
def test_emit(client, auth_header):
    r = client.post("/events/emit", json={"event_type": "expense.created"}, headers=auth_header)
    assert r.status_code == 201
    assert r.get_json()["event_type"] == "expense.created"
def test_stream(client, auth_header):
    client.post("/events/emit", json={"event_type": "test"}, headers=auth_header)
    r = client.get("/events/stream", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) >= 1
def test_types(client, auth_header):
    client.post("/events/emit", json={"event_type": "foo"}, headers=auth_header)
    r = client.get("/events/types", headers=auth_header)
    assert "foo" in r.get_json()["types"]
def test_filter(client, auth_header):
    client.post("/events/emit", json={"event_type": "alpha"}, headers=auth_header)
    client.post("/events/emit", json={"event_type": "beta"}, headers=auth_header)
    r = client.get("/events/stream?type=alpha", headers=auth_header)
    assert all(e["event_type"] == "alpha" for e in r.get_json())
