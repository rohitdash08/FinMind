"""Tests for cash flow forecasting."""
from datetime import date, timedelta

def _add(client, h, amt, desc, typ="EXPENSE", d=None):
    payload = {"amount": amt, "description": desc, "expense_type": typ}
    if d: payload["date"] = d
    r = client.post("/expenses", json=payload, headers=h)
    assert r.status_code == 201

def test_forecast_requires_auth(client):
    assert client.get("/forecast").status_code in (401, 422)

def test_forecast_empty(client, auth_header):
    r = client.get("/forecast", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["avg_daily_spend"] == 0

def test_forecast_with_data(client, auth_header):
    today = date.today()
    for i in range(5):
        _add(client, auth_header, 100, f"Expense {i}", "EXPENSE", (today - timedelta(days=i+1)).isoformat())
    _add(client, auth_header, 3000, "Salary", "INCOME", (today - timedelta(days=1)).isoformat())
    r = client.get("/forecast?months=3", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["forecast"]) == 3
    assert data["avg_daily_spend"] > 0
    assert data["avg_daily_income"] > 0

def test_forecast_months_param(client, auth_header):
    r = client.get("/forecast?months=6", headers=auth_header)
    assert r.status_code == 200

def test_forecast_structure(client, auth_header):
    _add(client, auth_header, 50, "Test", "EXPENSE")
    r = client.get("/forecast", headers=auth_header)
    data = r.get_json()
    if data["forecast"]:
        f = data["forecast"][0]
        assert "projected_income" in f
        assert "projected_expenses" in f
        assert "net_flow" in f
        assert "known_bills" in f

def test_forecast_max_12_months(client, auth_header):
    r = client.get("/forecast?months=99", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()["forecast"]) <= 12
