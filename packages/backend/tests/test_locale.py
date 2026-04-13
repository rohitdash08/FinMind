def test_auth(client): assert client.get("/locale/supported").status_code in (401, 422)
def test_supported(client, auth_header):
    r = client.get("/locale/supported", headers=auth_header)
    assert r.status_code == 200
    assert "en-US" in r.get_json()["locales"]
    assert len(r.get_json()["locales"]) >= 10
def test_config(client, auth_header):
    r = client.get("/locale/config?locale=en-US", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["currency"] == "USD"
def test_config_invalid(client, auth_header):
    r = client.get("/locale/config?locale=xx-YY", headers=auth_header)
    assert r.status_code == 400
def test_format_currency(client, auth_header):
    r = client.post("/locale/format", json={"value": 1234.56, "type": "currency", "locale": "en-US"}, headers=auth_header)
    assert r.status_code == 200
    assert "USD" in r.get_json()["formatted"]
def test_format_german(client, auth_header):
    r = client.post("/locale/format", json={"value": 1000, "type": "currency", "locale": "de-DE"}, headers=auth_header)
    assert r.status_code == 200
    assert "EUR" in r.get_json()["formatted"]
