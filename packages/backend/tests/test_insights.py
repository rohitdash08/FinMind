from datetime import date, timedelta


def test_weekly_summary_highlights_trends_and_insights(client, auth_header):
    week_start = date(2026, 2, 2)
    current_items = [
        ("Groceries", 120, week_start),
        ("Transport", 80, week_start + timedelta(days=2)),
        ("Paycheck", 500, week_start + timedelta(days=4), "INCOME"),
    ]
    previous_items = [
        ("Previous groceries", 100, week_start - timedelta(days=7)),
        ("Previous transport", 50, week_start - timedelta(days=5)),
    ]

    for item in current_items + previous_items:
        description, amount, spent_at, *expense_type = item
        r = client.post(
            "/expenses",
            json={
                "amount": amount,
                "description": description,
                "date": spent_at.isoformat(),
                "expense_type": expense_type[0] if expense_type else "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get(
        f"/insights/weekly-summary?week_start={week_start.isoformat()}",
        headers=auth_header,
    )

    assert r.status_code == 200
    payload = r.get_json()
    assert payload["week_start"] == "2026-02-02"
    assert payload["week_end"] == "2026-02-08"
    assert payload["total_expenses"] == 200.0
    assert payload["total_income"] == 500.0
    assert payload["net_flow"] == 300.0
    assert payload["transaction_count"] == 3
    assert payload["expense_change_pct"] == 33.33
    assert payload["top_categories"][0] == {"category_id": "uncat", "amount": 200.0}
    assert any("up 33.33%" in insight for insight in payload["trend_insights"])


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
