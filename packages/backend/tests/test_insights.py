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


def test_lifestyle_inflation_returns_expected_fields(client, auth_header):
    r = client.get("/insights/lifestyle-inflation", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "period_months" in payload
    assert "month_labels" in payload
    assert "inflation_score" in payload
    assert "rising_categories" in payload
    assert "total_rising" in payload
    assert isinstance(payload["month_labels"], list)


def test_lifestyle_inflation_detects_rising_spend(client, auth_header):
    today = date.today().replace(day=15)
    # Low spend 3 months ago
    old = today - timedelta(days=90)
    # High spend this month
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Old dining",
            "date": old.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "New dining",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/insights/lifestyle-inflation?months=6", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["inflation_score"] > 0


def test_lifestyle_inflation_months_clamped(client, auth_header):
    r = client.get("/insights/lifestyle-inflation?months=999", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["period_months"] <= 24

    r = client.get("/insights/lifestyle-inflation?months=0", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["period_months"] >= 2
