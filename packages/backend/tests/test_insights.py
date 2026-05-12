from datetime import date, timedelta


def _create_category(client, auth_header, name: str) -> int:
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()["id"]


def _create_transaction(
    client,
    auth_header,
    amount: float,
    description: str,
    spent_at: date,
    expense_type: str = "EXPENSE",
    category_id: int | None = None,
):
    payload = {
        "amount": amount,
        "description": description,
        "date": spent_at.isoformat(),
        "expense_type": expense_type,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def test_weekly_summary_returns_digest_trends_and_breakdowns(client, auth_header):
    week_start = date(2026, 5, 4)
    previous_week_start = week_start - timedelta(days=7)
    groceries = _create_category(client, auth_header, "Groceries")
    travel = _create_category(client, auth_header, "Travel")

    _create_transaction(
        client,
        auth_header,
        1000,
        "Paycheck",
        week_start,
        expense_type="INCOME",
    )
    _create_transaction(
        client,
        auth_header,
        250,
        "Weekly groceries",
        week_start + timedelta(days=1),
        category_id=groceries,
    )
    _create_transaction(
        client,
        auth_header,
        100,
        "Transit pass",
        week_start + timedelta(days=2),
        category_id=travel,
    )
    _create_transaction(
        client,
        auth_header,
        200,
        "Previous week groceries",
        previous_week_start + timedelta(days=1),
        category_id=groceries,
    )

    r = client.get(
        f"/insights/weekly-summary?week_start={week_start.isoformat()}",
        headers=auth_header,
    )

    assert r.status_code == 200
    payload = r.get_json()
    assert payload["period"]["week_start"] == "2026-05-04"
    assert payload["period"]["week_end"] == "2026-05-10"
    assert payload["summary"]["income"] == 1000.0
    assert payload["summary"]["expenses"] == 350.0
    assert payload["summary"]["net_flow"] == 650.0
    assert payload["summary"]["transaction_count"] == 3
    assert payload["comparison"]["previous_expenses"] == 200.0
    assert payload["comparison"]["expense_change_pct"] == 75.0
    assert len(payload["daily_breakdown"]) == 7
    assert payload["daily_breakdown"][1]["expenses"] == 250.0
    assert payload["category_breakdown"][0]["category_name"] == "Groceries"
    assert payload["category_breakdown"][0]["amount"] == 250.0
    assert payload["largest_expenses"][0]["description"] == "Weekly groceries"
    assert payload["highlights"]
    assert payload["insights"]
    assert payload["recommendations"]
    assert payload["method"] == "heuristic"


def test_weekly_summary_empty_week_returns_zero_activity_digest(client, auth_header):
    r = client.get(
        "/insights/weekly-summary?week_start=2026-05-04",
        headers=auth_header,
    )

    assert r.status_code == 200
    payload = r.get_json()
    assert payload["summary"]["transaction_count"] == 0
    assert payload["summary"]["income"] == 0.0
    assert payload["summary"]["expenses"] == 0.0
    assert payload["category_breakdown"] == []
    assert payload["largest_expenses"] == []
    assert payload["insights"][0]["type"] == "activity"


def test_weekly_summary_rejects_invalid_week_start(client, auth_header):
    r = client.get(
        "/insights/weekly-summary?week_start=2026-99-99", headers=auth_header
    )

    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid week_start, expected YYYY-MM-DD"


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
