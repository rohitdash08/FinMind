from datetime import date, timedelta

import pytest


class _MemoryRedis:
    def __init__(self):
        self.values = {}

    def setex(self, key, _ttl, value):
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
        return len(keys)

    def scan(self, cursor=0, match=None, count=None):
        return 0, []

    def flushdb(self):
        self.values.clear()
        return True


@pytest.fixture()
def auth_header_no_redis(client, monkeypatch):
    from app.routes import auth as auth_routes
    from app.services import cache as cache_service

    memory_redis = _MemoryRedis()
    monkeypatch.setattr(auth_routes, "redis_client", memory_redis)
    monkeypatch.setattr(cache_service, "redis_client", memory_redis)

    email = "weekly-digest@example.com"
    password = "password123"
    response = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code in (200, 201, 409)

    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    access = response.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


def test_weekly_digest_returns_summary_trends_and_upcoming_bills(
    client, auth_header_no_redis
):
    end = date(2026, 3, 14)
    current_week = end - timedelta(days=2)
    previous_week = end - timedelta(days=9)

    food = client.post(
        "/categories", json={"name": "Food"}, headers=auth_header_no_redis
    )
    assert food.status_code == 201
    food_id = food.get_json()["id"]

    current_rows = [
        {
            "amount": 1200,
            "description": "Salary",
            "date": current_week.isoformat(),
            "expense_type": "INCOME",
        },
        {
            "amount": 80,
            "description": "Groceries",
            "date": current_week.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
        {
            "amount": 40,
            "description": "Dinner",
            "date": (end - timedelta(days=1)).isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
    ]
    for row in current_rows:
        response = client.post("/expenses", json=row, headers=auth_header_no_redis)
        assert response.status_code == 201

    response = client.post(
        "/expenses",
        json={
            "amount": 60,
            "description": "Previous week groceries",
            "date": previous_week.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": food_id,
        },
        headers=auth_header_no_redis,
    )
    assert response.status_code == 201

    bill = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 50,
            "next_due_date": (end + timedelta(days=3)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header_no_redis,
    )
    assert bill.status_code == 201

    response = client.get(
        f"/insights/weekly-digest?end_date={end.isoformat()}",
        headers=auth_header_no_redis,
    )
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["period"]["start_date"] == "2026-03-08"
    assert payload["period"]["end_date"] == "2026-03-14"
    assert payload["summary"]["income"] == 1200.0
    assert payload["summary"]["expenses"] == 120.0
    assert payload["summary"]["net_flow"] == 1080.0
    assert payload["summary"]["transaction_count"] == 3
    assert payload["comparison"]["previous_expenses"] == 60.0
    assert payload["comparison"]["expense_change"] == 60.0
    assert payload["comparison"]["expense_change_pct"] == 100.0
    assert payload["top_categories"][0]["category_name"] == "Food"
    assert payload["top_categories"][0]["amount"] == 120.0
    assert payload["upcoming_bills"][0]["name"] == "Internet"
    assert any("Spending is up" in item for item in payload["insights"])


def test_weekly_digest_rejects_invalid_end_date(client, auth_header_no_redis):
    response = client.get(
        "/insights/weekly-digest?end_date=2026-99-99",
        headers=auth_header_no_redis,
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid end_date, expected YYYY-MM-DD"
