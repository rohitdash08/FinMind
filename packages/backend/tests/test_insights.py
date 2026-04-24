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


def test_weekly_summary_returns_trends_highlights_and_recommendations(client, auth_header):
    week_start = date(2026, 4, 6)
    previous_start = week_start - timedelta(days=7)

    r = client.post("/categories", json={"name": "Groceries"}, headers=auth_header)
    assert r.status_code == 201
    groceries_id = r.get_json()["id"]

    current_rows = [
        (2500, "Salary", week_start, "INCOME", None),
        (450, "Grocery stock-up", week_start + timedelta(days=1), "EXPENSE", groceries_id),
        (150, "Utilities", week_start + timedelta(days=2), "EXPENSE", None),
    ]
    previous_rows = [
        (100, "Previous groceries", previous_start + timedelta(days=1), "EXPENSE", groceries_id),
    ]
    for amount, description, spent_at, expense_type, category_id in current_rows + previous_rows:
        payload = {
            "amount": amount,
            "description": description,
            "date": spent_at.isoformat(),
            "expense_type": expense_type,
        }
        if category_id:
            payload["category_id"] = category_id
        r = client.post("/expenses", json=payload, headers=auth_header)
        assert r.status_code == 201

    r = client.post(
        "/bills",
        json={
            "name": "Rent",
            "amount": 1200,
            "next_due_date": (week_start + timedelta(days=8)).isoformat(),
            "cadence": "MONTHLY",
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

    assert payload["period"]["week_start"] == "2026-04-06"
    assert payload["period"]["week_end"] == "2026-04-12"
    assert payload["summary"]["income"] == 2500.0
    assert payload["summary"]["expenses"] == 600.0
    assert payload["summary"]["net_flow"] == 1900.0
    assert payload["summary"]["transactions_count"] == 3
    assert payload["summary"]["upcoming_bills_total"] == 1200.0
    assert payload["trends"]["expense_change_pct"] == 500.0
    assert payload["trends"]["top_category"] == "Groceries"
    assert payload["category_breakdown"][0]["category_name"] == "Groceries"
    assert payload["category_breakdown"][0]["share_pct"] == 75.0
    assert any("Top category" in item for item in payload["highlights"])
    assert any(item["type"] == "trend" for item in payload["insights"])
    assert any("Reserve cash" in item for item in payload["recommendations"])


def test_weekly_summary_rejects_invalid_week_start(client, auth_header):
    r = client.get("/insights/weekly-summary?week_start=not-a-date", headers=auth_header)
    assert r.status_code == 400
    assert "invalid week_start" in r.get_json()["error"]
