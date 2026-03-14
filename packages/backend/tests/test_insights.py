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


# ============ Weekly Summary Tests ============


def test_weekly_summary_returns_weekly_data(client, auth_header):
    """Test that weekly summary returns required fields."""
    # Add some expenses for the current week
    today = date.today()
    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Weekly expense 1",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 30,
            "description": "Weekly expense 2",
            "date": (today - timedelta(days=2)).isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # Check required fields
    assert "week_start" in payload
    assert "week_end" in payload
    assert "analytics" in payload
    assert "upcoming_bills" in payload
    assert "insights" in payload
    assert "tips" in payload
    assert "trend" in payload
    assert payload["method"] == "heuristic"


def test_weekly_summary_analytics_structure(client, auth_header):
    """Test that weekly analytics contains expected fields."""
    today = date.today()
    client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Test expense",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    analytics = payload["analytics"]

    # Check analytics fields
    assert "week_over_week_change_pct" in analytics
    assert "current_week_expenses" in analytics
    assert "previous_week_expenses" in analytics
    assert "current_week_income" in analytics
    assert "net_flow" in analytics
    assert "top_categories" in analytics
    assert "daily_spending" in analytics


def test_weekly_summary_with_bills(client, auth_header):
    """Test that upcoming bills are included in weekly summary."""
    today = date.today()
    due_date = (today + timedelta(days=3)).isoformat()

    # Create a bill due this week
    r = client.post(
        "/bills",
        json={
            "name": "Test Bill",
            "amount": 50,
            "next_due_date": due_date,
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # Check upcoming bills
    assert "upcoming_bills" in payload
    assert len(payload["upcoming_bills"]) >= 1
    assert payload["upcoming_bills"][0]["name"] == "Test Bill"


def test_weekly_summary_with_week_offset(client, auth_header):
    """Test that week_offset parameter works correctly."""
    today = date.today()

    # Add expense for this week
    client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Current week",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    # Get last week's summary (-1)
    r = client.get("/insights/weekly-summary?week=-1", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # Last week should have no expenses (or minimal)
    # Current week should show the expense we just added
    r_current = client.get("/insights/weekly-summary?week=0", headers=auth_header)
    payload_current = r_current.get_json()

    assert payload_current["analytics"]["current_week_expenses"] >= 100


def test_weekly_summary_prefers_user_gemini_key(client, auth_header, monkeypatch):
    """Test that user-provided Gemini API key is used."""
    captured = {}

    def _fake_gemini(uid, week_start, week_end, api_key, model, persona):
        captured["uid"] = uid
        captured["api_key"] = api_key
        captured["model"] = model
        return {
            "insights": ["AI insight"],
            "tips": ["AI tip"],
            "trend": "stable",
            "method": "gemini",
        }

    monkeypatch.setattr("app.services.ai._gemini_weekly_summary", _fake_gemini)

    r = client.get(
        "/insights/weekly-summary",
        headers={
            **auth_header,
            "X-Gemini-Api-Key": "user-gemini-key",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "gemini"
    assert captured["api_key"] == "user-gemini-key"


def test_weekly_summary_falls_back_when_gemini_fails(client, auth_header, monkeypatch):
    """Test fallback to heuristic when Gemini fails."""
    def _boom(*_args, **_kwargs):
        raise RuntimeError("gemini down")

    monkeypatch.setattr("app.services.ai._gemini_weekly_summary", _boom)

    r = client.get(
        "/insights/weekly-summary",
        headers={
            **auth_header,
            "X-Gemini-Api-Key": "user-supplied-key",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "heuristic"
    # Heuristic should still work
    assert "analytics" in payload
    assert "insights" in payload


def test_weekly_summary_with_income(client, auth_header):
    """Test that income is properly tracked in weekly summary."""
    today = date.today()

    # Add income
    client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Salary",
            "date": today.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )

    # Add expense
    client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Rent",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["analytics"]["current_week_income"] == 500
    assert payload["analytics"]["current_week_expenses"] == 200
    assert payload["analytics"]["net_flow"] == 300  # 500 - 200
