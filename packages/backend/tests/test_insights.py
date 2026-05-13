from datetime import date, timedelta


def _create_category(client, auth_header, name: str) -> int:
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()["id"]


def _create_transaction(
    client,
    auth_header,
    amount: float,
    description: str,
    spent_at: date,
    expense_type: str = "EXPENSE",
    category_id: int | None = None,
    currency: str = "USD",
):
    payload = {
        "amount": amount,
        "currency": currency,
        "description": description,
        "date": spent_at.isoformat(),
        "expense_type": expense_type,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def _auth_header_for(client, email: str) -> dict:
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def test_weekly_summary_requires_auth(client):
    r = client.get("/insights/weekly-summary?week_start=2026-05-04")
    assert r.status_code == 401


def test_weekly_summary_validates_monday_week_start(client, auth_header):
    r = client.get(
        "/insights/weekly-summary?week_start=2026-05-05",
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "week_start must be a Monday"

    r = client.get(
        "/insights/weekly-summary?week_start=not-a-date",
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid week_start, expected YYYY-MM-DD"


def test_weekly_summary_returns_empty_digest(client, auth_header):
    r = client.get(
        "/insights/weekly-summary?week_start=2026-05-04&currency=USD",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["period"]["week_start"] == "2026-05-04"
    assert payload["period"]["week_end"] == "2026-05-10"
    assert payload["period"]["currency"] == "USD"
    assert payload["summary"]["transaction_count"] == 0
    assert payload["summary"]["income"] == 0.0
    assert payload["summary"]["expenses"] == 0.0
    assert payload["daily_breakdown"][0]["date"] == "2026-05-04"
    assert payload["daily_breakdown"][-1]["date"] == "2026-05-10"
    assert payload["category_breakdown"] == []
    assert payload["largest_expenses"] == []
    assert payload["insights"][0]["type"] == "activity"
    assert payload["method"] == "heuristic"


def test_weekly_summary_aggregates_trends_bills_and_user_scope(client, auth_header):
    week_start = date(2026, 5, 4)
    food_id = _create_category(client, auth_header, "Food")
    travel_id = _create_category(client, auth_header, "Travel")

    _create_transaction(
        client,
        auth_header,
        1000,
        "Paycheck",
        week_start,
        expense_type="INCOME",
        currency="USD",
    )
    _create_transaction(
        client,
        auth_header,
        120,
        "Groceries",
        week_start,
        category_id=food_id,
        currency="USD",
    )
    _create_transaction(
        client,
        auth_header,
        80,
        "Dinner",
        week_start + timedelta(days=2),
        category_id=food_id,
        currency="USD",
    )
    _create_transaction(
        client,
        auth_header,
        50,
        "Taxi",
        week_start + timedelta(days=6),
        category_id=travel_id,
        currency="USD",
    )
    _create_transaction(
        client,
        auth_header,
        70,
        "Previous groceries",
        week_start - timedelta(days=6),
        category_id=food_id,
        currency="USD",
    )
    _create_transaction(
        client,
        auth_header,
        30,
        "Previous taxi",
        week_start - timedelta(days=4),
        category_id=travel_id,
        currency="USD",
    )
    _create_transaction(
        client,
        auth_header,
        999,
        "EUR hidden",
        week_start,
        currency="EUR",
    )

    other_header = _auth_header_for(client, "other@example.com")
    _create_transaction(
        client,
        other_header,
        500,
        "Other user hidden",
        week_start,
        currency="USD",
    )

    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 45,
            "currency": "USD",
            "next_due_date": "2026-05-09",
            "cadence": "MONTHLY",
            "autopay_enabled": True,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        "/insights/weekly-summary?week_start=2026-05-04&currency=USD",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"] == {
        "income": 1000.0,
        "expenses": 250.0,
        "net_flow": 750.0,
        "transaction_count": 4,
        "income_transaction_count": 1,
        "expense_transaction_count": 3,
        "average_daily_expense": 35.71,
        "savings_rate_pct": 75.0,
    }
    assert payload["comparison"]["previous_expenses"] == 100.0
    assert payload["comparison"]["expense_delta"] == 150.0
    assert payload["comparison"]["expense_change_pct"] == 150.0

    categories = payload["category_breakdown"]
    assert categories[0]["category_name"] == "Food"
    assert categories[0]["amount"] == 200.0
    assert categories[0]["share_pct"] == 80.0
    assert categories[0]["previous_amount"] == 70.0
    assert categories[0]["change_amount"] == 130.0
    assert categories[1]["category_name"] == "Travel"
    assert categories[1]["previous_amount"] == 30.0

    assert payload["category_trends"][0]["category_name"] == "Food"
    assert payload["category_trends"][0]["trend"] == "up"

    by_date = {item["date"]: item for item in payload["daily_breakdown"]}
    assert by_date["2026-05-04"]["income"] == 1000.0
    assert by_date["2026-05-04"]["expenses"] == 120.0
    assert by_date["2026-05-06"]["expenses"] == 80.0
    assert by_date["2026-05-10"]["expenses"] == 50.0

    assert payload["largest_expenses"][0]["description"] == "Groceries"
    assert payload["largest_expenses"][0]["amount"] == 120.0
    assert payload["upcoming_bills"][0]["name"] == "Internet"
    assert payload["upcoming_bills"][0]["autopay_enabled"] is True

    insight_types = {item["type"] for item in payload["insights"]}
    assert {
        "top_category",
        "cash_flow",
        "spending_increase",
        "category_trend",
        "daily_trend",
        "upcoming_bills",
    }.issubset(insight_types)
    assert any("surplus" in item for item in payload["recommendations"])


def test_budget_suggestion_returns_analytics_fields(client, auth_header):
    current = date.today().replace(day=10)
    previous = (current.replace(day=1) - timedelta(days=1)).replace(day=10)

    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Current month spend",
            "date": current.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Previous month spend",
            "date": previous.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    ym = current.strftime("%Y-%m")
    r = client.get(f"/insights/budget-suggestion?month={ym}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "analytics" in payload
    assert "month_over_month_change_pct" in payload["analytics"]
    assert payload["month"] == ym


def test_budget_suggestion_prefers_user_gemini_key(client, auth_header, monkeypatch):
    captured = {}

    def _fake_gemini(uid, ym, api_key, model, persona):
        captured["uid"] = uid
        captured["ym"] = ym
        captured["api_key"] = api_key
        captured["model"] = model
        captured["persona"] = persona
        return {
            "suggested_total": 777.0,
            "breakdown": {"needs": 300, "wants": 200, "savings": 277},
            "tips": ["Tip 1", "Tip 2"],
            "method": "gemini",
        }

    monkeypatch.setattr("app.services.ai._gemini_budget_suggestion", _fake_gemini)

    r = client.get(
        "/insights/budget-suggestion",
        headers={
            **auth_header,
            "X-Gemini-Api-Key": "user-supplied-key",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "gemini"
    assert payload["suggested_total"] == 777.0
    assert captured["api_key"] == "user-supplied-key"


def test_budget_suggestion_falls_back_when_gemini_fails(
    client, auth_header, monkeypatch
):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("gemini down")

    monkeypatch.setattr("app.services.ai._gemini_budget_suggestion", _boom)

    r = client.get(
        "/insights/budget-suggestion",
        headers={
            **auth_header,
            "X-Gemini-Api-Key": "user-supplied-key",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "heuristic"
    assert "warnings" in payload
    assert "gemini_unavailable" in payload["warnings"]
