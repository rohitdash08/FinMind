from datetime import date, timedelta


def test_weekly_summary_returns_trends_categories_and_bills(client, auth_header):
    monday = date(2026, 5, 18)

    r = client.post("/categories", json={"name": "Groceries"}, headers=auth_header)
    assert r.status_code == 201
    groceries_id = r.get_json()["id"]

    r = client.post(
        "/expenses",
        json={
            "amount": 240,
            "description": "Weekly paycheck",
            "date": monday.isoformat(),
            "expense_type": "INCOME",
            "currency": "USD",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    r = client.post(
        "/expenses",
        json={
            "amount": 60,
            "description": "Market run",
            "date": (monday + timedelta(days=1)).isoformat(),
            "expense_type": "EXPENSE",
            "currency": "USD",
            "category_id": groceries_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    r = client.post(
        "/expenses",
        json={
            "amount": 40,
            "description": "Previous market run",
            "date": (monday - timedelta(days=6)).isoformat(),
            "expense_type": "EXPENSE",
            "currency": "USD",
            "category_id": groceries_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 70,
            "currency": "USD",
            "next_due_date": (monday + timedelta(days=3)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        f"/insights/weekly-summary?week_start={monday.isoformat()}&currency=USD",
        headers=auth_header,
    )

    assert r.status_code == 200
    payload = r.get_json()
    assert payload["period"]["week_start"] == "2026-05-18"
    assert payload["period"]["week_end"] == "2026-05-24"
    assert payload["currency"] == "USD"
    assert payload["summary"]["income"] == 240.0
    assert payload["summary"]["expenses"] == 60.0
    assert payload["summary"]["net_flow"] == 180.0
    assert payload["comparison"]["previous_expenses"] == 40.0
    assert payload["comparison"]["trend"] == "up"
    assert payload["category_breakdown"][0]["category_name"] == "Groceries"
    assert payload["category_breakdown"][0]["share_pct"] == 100.0
    assert len(payload["daily_breakdown"]) == 7
    assert payload["upcoming_bills"][0]["name"] == "Internet"
    assert payload["largest_expenses"][0]["description"] == "Market run"
    assert payload["highlights"]
    assert payload["insights"]
    assert payload["recommendations"]


def test_weekly_summary_normalizes_dates_and_rejects_bad_dates(client, auth_header):
    r = client.get(
        "/insights/weekly-summary?week_start=2026-05-21",
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["period"]["week_start"] == "2026-05-18"

    r = client.get(
        "/insights/weekly-summary?week_start=not-a-date",
        headers=auth_header,
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid week_start"


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
