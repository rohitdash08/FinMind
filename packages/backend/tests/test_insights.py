from datetime import date, timedelta


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


def test_weekly_summary_requires_auth(client):
    r = client.get("/insights/weekly-summary?week_start=2026-05-04")
    assert r.status_code == 401


def test_weekly_summary_validates_monday_week_start(client, auth_header):
    r = client.get(
        "/insights/weekly-summary?week_start=2026-05-05", headers=auth_header
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "week_start must be a Monday"


def test_weekly_summary_returns_empty_digest(client, auth_header):
    r = client.get(
        "/insights/weekly-summary?week_start=2026-05-04", headers=auth_header
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["period"]["week_start"] == "2026-05-04"
    assert payload["summary"]["expenses"] == 0.0
    assert payload["summary"]["income"] == 0.0
    assert payload["daily_breakdown"][0]["date"] == "2026-05-04"
    assert payload["daily_breakdown"][-1]["date"] == "2026-05-10"
    assert payload["insights"][0]["type"] == "empty_week"


def test_weekly_summary_aggregates_categories_days_previous_week_and_bills(
    client, auth_header
):
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]

    r = client.post("/categories", json={"name": "Travel"}, headers=auth_header)
    assert r.status_code == 201
    travel_id = r.get_json()["id"]

    expenses = [
        (1000, "Salary", "2026-05-04", "INCOME", None),
        (120, "Groceries", "2026-05-04", "EXPENSE", food_id),
        (80, "Dinner", "2026-05-06", "EXPENSE", food_id),
        (50, "Taxi", "2026-05-10", "EXPENSE", travel_id),
        (70, "Previous groceries", "2026-04-28", "EXPENSE", food_id),
        (999, "EUR hidden", "2026-05-04", "EXPENSE", None),
    ]
    for amount, description, spent_at, expense_type, category_id in expenses:
        payload = {
            "amount": amount,
            "currency": "EUR" if description == "EUR hidden" else "USD",
            "description": description,
            "date": spent_at,
            "expense_type": expense_type,
        }
        if category_id is not None:
            payload["category_id"] = category_id
        r = client.post("/expenses", json=payload, headers=auth_header)
        assert r.status_code == 201

    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 45,
            "currency": "USD",
            "next_due_date": "2026-05-09",
            "cadence": "MONTHLY",
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

    assert payload["period"]["currency"] == "USD"
    assert payload["summary"] == {
        "income": 1000.0,
        "expenses": 250.0,
        "net_flow": 750.0,
        "transaction_count": 4,
        "average_daily_expense": 35.71,
    }
    assert payload["previous_week"]["expenses"] == 70.0
    assert payload["previous_week"]["expense_delta"] == 180.0
    assert payload["previous_week"]["expense_delta_pct"] == 257.14

    categories = payload["category_breakdown"]
    assert categories[0]["category_name"] == "Food"
    assert categories[0]["amount"] == 200.0
    assert categories[0]["transaction_count"] == 2
    assert categories[0]["share_pct"] == 80.0
    assert categories[0]["previous_amount"] == 70.0
    assert categories[1]["category_name"] == "Travel"

    by_date = {item["date"]: item for item in payload["daily_breakdown"]}
    assert by_date["2026-05-04"]["income"] == 1000.0
    assert by_date["2026-05-04"]["expenses"] == 120.0
    assert by_date["2026-05-06"]["expenses"] == 80.0
    assert by_date["2026-05-10"]["expenses"] == 50.0

    assert payload["upcoming_bills"][0]["name"] == "Internet"
    insight_types = {item["type"] for item in payload["insights"]}
    assert {
        "top_category",
        "spending_increase",
        "upcoming_bills",
        "positive_cash_flow",
    }.issubset(insight_types)
