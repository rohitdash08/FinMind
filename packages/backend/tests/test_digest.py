import pytest


class _FakeRedis:
    def __init__(self):
        self._data = {}

    def setex(self, key, _ttl, value):
        self._data[key] = value
        return True

    def get(self, key):
        return self._data.get(key)

    def delete(self, *keys):
        removed = 0
        for key in keys:
            removed += int(key in self._data)
            self._data.pop(key, None)
        return removed

    def scan_iter(self, match=None):
        return []

    def scan(self, cursor=0, match=None, count=None):
        return 0, []


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("app.routes.auth.redis_client", fake)
    monkeypatch.setattr("app.services.cache.redis_client", fake)


def _create_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    for item in r.get_json():
        if item["name"] == name:
            return item["id"]
    raise AssertionError(f"category {name!r} not found")


def test_weekly_digest_requires_jwt(client):
    r = client.get("/digest/weekly?date=2026-02-12")
    assert r.status_code == 401


def test_weekly_digest_returns_financial_summary_for_anchor_week(client, auth_header):
    groceries_id = _create_category(client, auth_header, "Groceries")
    salary_id = _create_category(client, auth_header, "Salary")

    expenses = [
        {
            "amount": 45.50,
            "currency": "USD",
            "category_id": groceries_id,
            "description": "Groceries",
            "date": "2026-02-09",
            "expense_type": "EXPENSE",
        },
        {
            "amount": 12.25,
            "currency": "USD",
            "category_id": groceries_id,
            "description": "Coffee",
            "date": "2026-02-11",
            "expense_type": "EXPENSE",
        },
        {
            "amount": 1000,
            "currency": "USD",
            "category_id": salary_id,
            "description": "Paycheck",
            "date": "2026-02-13",
            "expense_type": "INCOME",
        },
        {
            "amount": 20,
            "currency": "USD",
            "category_id": groceries_id,
            "description": "Previous groceries",
            "date": "2026-02-04",
            "expense_type": "EXPENSE",
        },
        {
            "amount": 30,
            "currency": "USD",
            "description": "Previous uncategorized",
            "date": "2026-02-05",
            "expense_type": "EXPENSE",
        },
        {
            "amount": 999,
            "currency": "USD",
            "description": "Outside selected week",
            "date": "2026-02-16",
            "expense_type": "EXPENSE",
        },
    ]
    for payload in expenses:
        r = client.post("/expenses", json=payload, headers=auth_header)
        assert r.status_code == 201

    r = client.post(
        "/bills",
        json={
            "name": "Electricity",
            "amount": 80,
            "currency": "USD",
            "next_due_date": "2026-02-15",
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/digest/weekly?date=2026-02-12&currency=USD", headers=auth_header)
    assert r.status_code == 200
    digest = r.get_json()

    assert digest["period"] == {
        "start_date": "2026-02-09",
        "end_date": "2026-02-15",
    }
    assert digest["currency"] == "USD"
    assert digest["totals"] == {
        "income": 1000.0,
        "expenses": 57.75,
        "net_cash_flow": 942.25,
        "transaction_count": 3,
    }
    assert digest["comparison"] == {
        "previous_period": {
            "start_date": "2026-02-02",
            "end_date": "2026-02-08",
        },
        "previous_expenses": 50.0,
        "expense_delta": 7.75,
        "expense_percent_change": 15.5,
    }
    assert digest["category_trends"] == [
        {
            "category": "Groceries",
            "current_amount": 57.75,
            "previous_amount": 20.0,
            "delta": 37.75,
            "percent_change": 188.75,
            "trend": "up",
        },
        {
            "category": "Uncategorized",
            "current_amount": 0.0,
            "previous_amount": 30.0,
            "delta": -30.0,
            "percent_change": -100.0,
            "trend": "down",
        },
    ]
    assert digest["category_breakdown"] == [
        {"category": "Groceries", "amount": 57.75, "transaction_count": 2}
    ]
    assert digest["top_expenses"][0]["description"] == "Groceries"
    assert digest["top_expenses"][0]["amount"] == 45.5
    assert digest["upcoming_bills"] == [
        {
            "id": 1,
            "name": "Electricity",
            "amount": 80.0,
            "currency": "USD",
            "due_date": "2026-02-15",
            "cadence": "MONTHLY",
        }
    ]
    assert digest["highlights"][0] == "You ended the week positive by USD 942.25."
    assert any(
        "Groceries was your highest spending category" in item
        for item in digest["highlights"]
    )


def test_weekly_digest_defaults_currency_to_user_preference_and_validates_date(
    client, auth_header
):
    r = client.patch(
        "/auth/me", json={"preferred_currency": "EUR"}, headers=auth_header
    )
    assert r.status_code == 200

    r = client.post(
        "/expenses",
        json={
            "amount": 25,
            "description": "Transit",
            "currency": "EUR",
            "date": "2026-03-03",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/digest/weekly?date=2026-03-04", headers=auth_header)
    assert r.status_code == 200
    digest = r.get_json()
    assert digest["currency"] == "EUR"
    assert digest["totals"]["expenses"] == 25.0

    r = client.get("/digest/weekly?date=not-a-date", headers=auth_header)
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid date"
