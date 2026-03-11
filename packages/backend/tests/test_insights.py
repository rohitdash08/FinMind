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


def test_weekly_digest_returns_current_week_data(client, auth_header):
    """Test that weekly digest returns proper weekly data."""
    from datetime import datetime, timedelta
    
    today = date.today()
    # Get start of current week (Monday)
    monday = today - timedelta(days=today.weekday())
    
    # Add some expenses for this week
    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Weekly expense",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "week_start" in payload
    assert "week_end" in payload
    assert "income" in payload
    assert "expenses" in payload
    assert "net_flow" in payload
    assert "savings_rate_pct" in payload
    assert "category_breakdown" in payload
    assert "tips" in payload
    assert "analytics" in payload
    assert payload["method"] in ["gemini", "heuristic"]


def test_weekly_digest_analytics_structure(client, auth_header):
    """Test that weekly digest analytics has correct structure."""
    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    analytics = payload["analytics"]
    assert "week_over_week_change_pct" in analytics
    assert "current_week_expenses" in analytics
    assert "previous_week_expenses" in analytics
    assert "top_categories" in analytics


def test_weekly_digest_supports_weeks_ago_parameter(client, auth_header):
    """Test that weekly digest accepts weeks_ago parameter."""
    r = client.get("/insights/weekly-digest?weeks_ago=1", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "week_start" in payload
