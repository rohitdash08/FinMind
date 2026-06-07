from datetime import date, timedelta


def _create_category(client, auth_header, name="Groceries"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()["id"]


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


def test_weekly_summary_returns_trends_categories_and_bills(client, auth_header):
    groceries_id = _create_category(client, auth_header, "Groceries")
    dining_id = _create_category(client, auth_header, "Dining")

    # The endpoint normalizes any requested date to its ISO week Monday.
    week_start = date(2026, 3, 2)
    prior_week = week_start - timedelta(days=7)
    payloads = [
        {
            "amount": 120,
            "description": "Grocery stock-up",
            "date": week_start.isoformat(),
            "category_id": groceries_id,
            "expense_type": "EXPENSE",
        },
        {
            "amount": 80,
            "description": "Dinner",
            "date": (week_start + timedelta(days=2)).isoformat(),
            "category_id": dining_id,
            "expense_type": "EXPENSE",
        },
        {
            "amount": 500,
            "description": "Paycheck",
            "date": (week_start + timedelta(days=4)).isoformat(),
            "expense_type": "INCOME",
        },
        {
            "amount": 100,
            "description": "Prior groceries",
            "date": prior_week.isoformat(),
            "category_id": groceries_id,
            "expense_type": "EXPENSE",
        },
    ]
    for payload in payloads:
        r = client.post("/expenses", json=payload, headers=auth_header)
        assert r.status_code == 201

    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 60,
            "next_due_date": (week_start + timedelta(days=5)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        "/insights/weekly-summary?week_start=2026-03-05",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["week_start"] == "2026-03-02"
    assert payload["week_end"] == "2026-03-08"
    assert payload["currency"] == "INR"
    assert payload["totals"]["expenses"] == 200.0
    assert payload["totals"]["income"] == 500.0
    assert payload["totals"]["net_flow"] == 300.0
    assert payload["previous_week"]["expenses"] == 100.0
    assert payload["previous_week"]["change_pct"] == 100.0
    assert payload["daily"][0]["expenses"] == 120.0
    assert payload["daily"][4]["income"] == 500.0
    assert payload["categories"][0]["category"] == "Groceries"
    assert payload["categories"][0]["amount"] == 120.0
    assert payload["categories"][0]["previous_amount"] == 100.0
    assert payload["top_expenses"][0]["description"] == "Grocery stock-up"
    assert payload["upcoming_bills"][0]["name"] == "Internet"
    assert any("Weekly spending" in item for item in payload["insights"])


def test_weekly_summary_rejects_invalid_week_start(client, auth_header):
    r = client.get(
        "/insights/weekly-summary?week_start=not-a-date",
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "week_start must be YYYY-MM-DD"


def test_weekly_summary_requires_authentication(client):
    r = client.get("/insights/weekly-summary")
    assert r.status_code == 401
