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


def test_weekly_digest_returns_trends_bills_and_recommendations(client, auth_header):
    week_start = date(2026, 6, 1)

    category = client.post(
        "/categories",
        json={"name": "Groceries"},
        headers=auth_header,
    )
    assert category.status_code == 201
    category_id = category.get_json()["id"]

    for amount, day, description in [
        (120, week_start, "Weekly groceries"),
        (60, week_start + timedelta(days=2), "Pantry restock"),
        (200, week_start - timedelta(days=3), "Previous week groceries"),
    ]:
        response = client.post(
            "/expenses",
            json={
                "amount": amount,
                "description": description,
                "date": day.isoformat(),
                "expense_type": "EXPENSE",
                "category_id": category_id,
                "currency": "USD",
            },
            headers=auth_header,
        )
        assert response.status_code == 201

    bill = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 75,
            "currency": "USD",
            "next_due_date": (week_start + timedelta(days=4)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert bill.status_code == 201

    response = client.get(
        f"/insights/weekly-digest?week={week_start.isoformat()}&currency=USD",
        headers=auth_header,
    )
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["week_start"] == week_start.isoformat()
    assert payload["week_end"] == (week_start + timedelta(days=6)).isoformat()
    assert payload["currency"] == "USD"
    assert payload["summary"]["expenses"] == 180
    assert payload["summary"]["net_flow"] == -180
    assert payload["summary"]["category_breakdown"][0] == {
        "category": "Groceries",
        "amount": 180,
    }
    assert payload["previous_week"]["expenses"] == 200
    assert payload["week_over_week_change_pct"] == -10
    assert payload["upcoming_bills"][0]["name"] == "Internet"
    assert payload["insights"]
    assert payload["recommendations"]
    assert payload["method"] == "deterministic"


def test_weekly_digest_rejects_invalid_week(client, auth_header):
    response = client.get(
        "/insights/weekly-digest?week=not-a-date", headers=auth_header
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid week"
