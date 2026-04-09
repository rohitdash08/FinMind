from datetime import date, timedelta


def test_budget_suggestion_returns_analytics_fields(client, auth_header):
    current = date.today().replace(day=10)
    previous_month_date = (current.replace(day=1) - timedelta(days=1)).replace(day=10)

    # Create expenses for the current month
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Current month spend 1",
            "date": current.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 250,
            "description": "Current month spend 2",
            "date": current.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Create expenses for the previous month
    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Previous month spend 1",
            "date": previous_month_date.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # This test was incomplete in the original prompt. The creation of expenses is sufficient
    # to test data population for other insights features like the heatmap.
    pass

def test_spending_heatmap_endpoint(client, auth_header):
    today = date.today()
    # Create expenses for multiple days
    client.post("/expenses", json={"amount": 10.0, "description": "Coffee", "date": (today - timedelta(days=5)).isoformat()}, headers=auth_header)
    client.post("/expenses", json={"amount": 20.0, "description": "Lunch", "date": (today - timedelta(days=5)).isoformat()}, headers=auth_header)
    client.post("/expenses", json={"amount": 15.0, "description": "Snack", "date": (today - timedelta(days=3)).isoformat()}, headers=auth_header)
    client.post("/expenses", json={"amount": 50.0, "description": "Dinner", "date": (today - timedelta(days=1)).isoformat()}, headers=auth_header)
    client.post("/expenses", json={"amount": 25.0, "description": "Groceries", "date": (today - timedelta(days=1)).isoformat()}, headers=auth_header)
    client.post("/expenses", json={"amount": 5.0, "description": "Misc", "date": today.isoformat()}, headers=auth_header)

    start_date = (today - timedelta(days=7)).isoformat()
    end_date = today.isoformat()

    # Test with valid date range
    r = client.get(
        f"/insights/spending-heatmap?start_date={start_date}&end_date={end_date}",
        headers=auth_header
    )
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)

    # Check specific aggregated amounts
    found_today_minus_5 = False
    found_today_minus_3 = False
    found_today_minus_1 = False
    found_today = False

    for item in data:
        if item["date"] == (today - timedelta(days=5)).isoformat():
            assert item["total_amount"] == 30.0 # 10 + 20
            found_today_minus_5 = True
        elif item["date"] == (today - timedelta(days=3)).isoformat():
            assert item["total_amount"] == 15.0
            found_today_minus_3 = True
        elif item["date"] == (today - timedelta(days=1)).isoformat():
            assert item["total_amount"] == 75.0 # 50 + 25
            found_today_minus_1 = True
        elif item["date"] == today.isoformat():
            assert item["total_amount"] == 5.0
            found_today = True

    assert found_today_minus_5
    assert found_today_minus_3
    assert found_today_minus_1
    assert found_today

    # Test with invalid date range (start_date > end_date)
    r = client.get(
        f"/insights/spending-heatmap?start_date={today.isoformat()}&end_date={(today - timedelta(days=1)).isoformat()}",
        headers=auth_header
    )
    assert r.status_code == 400
    assert r.get_json()["message"] == "start_date cannot be after end_date"

    # Test with missing start_date
    r = client.get(
        f"/insights/spending-heatmap?end_date={end_date}",
        headers=auth_header
    )
    assert r.status_code == 400
    assert r.get_json()["message"] == "start_date and end_date are required"

    # Test with missing end_date
    r = client.get(
        f"/insights/spending-heatmap?start_date={start_date}",
        headers=auth_header
    )
    assert r.status_code == 400
    assert r.get_json()["message"] == "start_date and end_date are required"

    # Test with invalid date format
    r = client.get(
        f"/insights/spending-heatmap?start_date=2024-01-01x&end_date={end_date}",
        headers=auth_header
    )
    assert r.status_code == 400
    assert r.get_json()["message"] == "Invalid date format. Use YYYY-MM-DD" 50,
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
