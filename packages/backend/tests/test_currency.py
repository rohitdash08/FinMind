"""Tests for multi-currency conversion."""

from app.services.currency import convert, get_supported_currencies, convert_all


# 1. Auth required
def test_currency_requires_auth(client):
    r = client.get("/currency/supported")
    assert r.status_code in (401, 422)


# 2. List supported currencies
def test_supported_currencies(client, auth_header):
    r = client.get("/currency/supported", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "USD" in data["currencies"]
    assert "INR" in data["currencies"]
    assert "EUR" in data["currencies"]
    assert len(data["currencies"]) >= 20


# 3. Convert USD to INR
def test_convert_usd_to_inr(client, auth_header):
    r = client.get("/currency/convert?amount=100&from=USD&to=INR", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["from"] == "USD"
    assert data["to"] == "INR"
    assert data["converted"] > 8000  # 100 USD > 8000 INR


# 4. Same currency = 1:1
def test_same_currency():
    result = convert(100, "USD", "USD")
    assert result["rate"] == 1.0
    assert result["converted"] == 100


# 5. Convert all
def test_convert_all():
    results = convert_all(100, "USD")
    assert len(results) >= 20
    inr = next(r for r in results if r["to"] == "INR")
    assert inr["converted"] > 8000


# 6. Invalid currency returns error
def test_invalid_currency(client, auth_header):
    r = client.get("/currency/convert?amount=100&from=XYZ&to=USD", headers=auth_header)
    assert r.status_code == 400


# 7. Missing params returns 400
def test_missing_params(client, auth_header):
    r = client.get("/currency/convert?amount=100", headers=auth_header)
    assert r.status_code == 400


# 8. Reverse conversion
def test_reverse_conversion():
    fwd = convert(100, "USD", "EUR")
    rev = convert(fwd["converted"], "EUR", "USD")
    assert abs(rev["converted"] - 100) < 1  # round-trip within 1 unit


# 9. Convert-all endpoint
def test_convert_all_endpoint(client, auth_header):
    r = client.get("/currency/convert-all?amount=1000&from=INR", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["base_currency"] == "INR"
    assert len(data["conversions"]) >= 20


# 10. Case insensitive
def test_case_insensitive(client, auth_header):
    r = client.get("/currency/convert?amount=50&from=usd&to=eur", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["from"] == "USD"
