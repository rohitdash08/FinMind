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


def test_weekly_digest_returns_financial_summary(client, auth_header):
    week_start = date.today() - timedelta(days=date.today().weekday())
    previous_week = week_start - timedelta(days=7)

    for amount, description, spent_at, expense_type in [
        (1200, "Paycheck", week_start, "INCOME"),
        (180, "Groceries", week_start + timedelta(days=1), "EXPENSE"),
        (70, "Transport", week_start + timedelta(days=2), "EXPENSE"),
        (200, "Previous week groceries", previous_week, "EXPENSE"),
    ]:
        r = client.post(
            "/expenses",
            json={
                "amount": amount,
                "description": description,
                "date": spent_at.isoformat(),
                "expense_type": expense_type,
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get(
        f"/insights/weekly-digest?week_start={week_start.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["week_start"] == week_start.isoformat()
    assert payload["week_end"] == (week_start + timedelta(days=6)).isoformat()
    assert payload["total_income"] == 1200
    assert payload["total_expenses"] == 250
    assert payload["net_flow"] == 950
    assert len(payload["daily_totals"]) == 7
    assert payload["previous_week"]["total_expenses"] == 200
    assert payload["trend"]["expense_change_pct"] == 25
    assert payload["top_categories"][0]["category_name"] == "Uncategorized"
    assert payload["insights"]
    assert payload["recommended_actions"]


def test_weekly_digest_rejects_invalid_week_start(client, auth_header):
    r = client.get("/insights/weekly-digest?week_start=not-a-date", headers=auth_header)
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid week_start"
