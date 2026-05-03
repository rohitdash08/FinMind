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


def test_weekly_digest_returns_correct_fields(client, auth_header):
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # Add expense to current week
    r = client.post(
        "/expenses",
        json={
            "amount": 200.0,
            "description": "Weekly spend",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Add expense to previous week for comparison
    prev_monday = monday - timedelta(days=7)
    r = client.post(
        "/expenses",
        json={
            "amount": 100.0,
            "description": "Prev week spend",
            "date": prev_monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        f"/insights/weekly-digest?start_date={monday.isoformat()}", headers=auth_header
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert "summary" in payload
    assert "highlights" in payload
    assert "insights" in payload
    assert "analytics" in payload
    assert payload["analytics"]["total_expenses"] == 200.0
    assert payload["analytics"]["change_vs_prev_week_pct"] == 100.0
    assert "period" in payload
    assert payload["period"]["start"] == monday.isoformat()
