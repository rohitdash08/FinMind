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


def test_weekly_summary_returns_totals_trends_and_daily(client, auth_header):
    week_end = date(2026, 3, 1)

    previous_week_entries = [
        {
            "amount": 1000,
            "expense_type": "INCOME",
            "date": "2026-02-17",
            "description": "salary",
        },
        {
            "amount": 300,
            "expense_type": "EXPENSE",
            "date": "2026-02-18",
            "description": "rent",
        },
        {
            "amount": 100,
            "expense_type": "EXPENSE",
            "date": "2026-02-20",
            "description": "food",
        },
    ]
    current_week_entries = [
        {
            "amount": 1200,
            "expense_type": "INCOME",
            "date": "2026-02-24",
            "description": "salary",
        },
        {
            "amount": 250,
            "expense_type": "EXPENSE",
            "date": "2026-02-25",
            "description": "rent",
        },
        {
            "amount": 50,
            "expense_type": "EXPENSE",
            "date": "2026-02-28",
            "description": "groceries",
        },
    ]

    for payload in [*previous_week_entries, *current_week_entries]:
        response = client.post("/expenses", json=payload, headers=auth_header)
        assert response.status_code == 201

    response = client.get(
        f"/insights/weekly-summary?end_date={week_end.isoformat()}",
        headers=auth_header,
    )
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["period"] == {
        "start_date": "2026-02-23",
        "end_date": "2026-03-01",
        "days": 7,
    }
    assert payload["totals"]["income"] == 1200.0
    assert payload["totals"]["expenses"] == 300.0
    assert payload["totals"]["net_flow"] == 900.0
    assert payload["trends"]["expenses_change_pct"] == -25.0
    assert payload["trends"]["income_change_pct"] == 20.0
    assert len(payload["daily"]) == 7
    assert payload["daily"][0]["date"] == "2026-02-23"
    assert len(payload["insights"]) >= 1
    assert payload["method"] == "heuristic"


def test_weekly_summary_rejects_invalid_end_date(client, auth_header):
    response = client.get(
        "/insights/weekly-summary?end_date=03-01-2026",
        headers=auth_header,
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert "invalid end_date" in payload["error"]
