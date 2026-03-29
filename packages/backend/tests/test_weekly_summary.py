from datetime import date, timedelta


def test_weekly_summary_returns_required_fields(client, auth_header):
    today = date.today()
    year, week_num, _ = today.isocalendar()
    current_week = f"{year}-W{week_num:02d}"
    
    # Add current week expense
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Groceries",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Add previous week expense
    prev_week_date = today - timedelta(days=7)
    r = client.post(
        "/expenses",
        json={
            "amount": 80,
            "description": "Dining out",
            "date": prev_week_date.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Get weekly summary
    r = client.get(f"/insights/weekly-summary?week={current_week}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # Verify required fields
    assert payload["week"] == current_week
    assert "week_start" in payload
    assert "week_end" in payload
    assert "total_income" in payload
    assert "total_expenses" in payload
    assert payload["total_expenses"] == 100.0
    assert "net_flow" in payload
    assert "analytics" in payload
    assert "insights" in payload
    assert isinstance(payload["insights"], list)
    assert "tips" in payload
    assert isinstance(payload["tips"], list)
    assert "method" in payload
    assert payload["method"] == "heuristic"
    
    # Verify analytics fields
    analytics = payload["analytics"]
    assert "week_over_week_change_pct" in analytics
    assert analytics["current_week_expenses"] == 100.0
    assert analytics["previous_week_expenses"] == 80.0
    assert "top_categories" in analytics
    assert "unusual_spend" in analytics
    assert "week_start" in analytics
    assert "week_end" in analytics


def test_weekly_summary_defaults_to_current_week(client, auth_header):
    today = date.today()
    year, week_num, _ = today.isocalendar()
    expected_week = f"{year}-W{week_num:02d}"
    
    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["week"] == expected_week


def test_weekly_summary_unusual_spend_detection(client, auth_header):
    today = date.today()
    year, week_num, _ = today.isocalendar()
    current_week = f"{year}-W{week_num:02d}"
    
    # Add 2x more spend than previous week in same category
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Electronics",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": 1,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    prev_week_date = today - timedelta(days=7)
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Previous electronics",
            "date": prev_week_date.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": 1,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    r = client.get(f"/insights/weekly-summary?week={current_week}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    # Check unusual spend is detected
    unusual = payload["analytics"]["unusual_spend"]
    assert len(unusual) >= 1
    assert unusual[0]["category_id"] == "1"
    assert unusual[0]["current_amount"] == 200.0
    assert unusual[0]["previous_amount"] == 100.0
    assert unusual[0]["increase_pct"] == 100.0


def test_weekly_summary_prefers_user_gemini_key(client, auth_header, monkeypatch):
    captured = {}
    
    def _fake_gemini(uid, week, api_key, model, persona):
        captured["uid"] = uid
        captured["week"] = week
        captured["api_key"] = api_key
        captured["model"] = model
        captured["persona"] = persona
        return {
            "week": "2024-W10",
            "week_start": "2024-03-04",
            "week_end": "2024-03-10",
            "total_income": 1000.0,
            "total_expenses": 700.0,
            "net_flow": 300.0,
            "analytics": {},
            "insights": ["Spending is on track"],
            "tips": ["Save more next week"],
            "method": "gemini",
        }
    
    monkeypatch.setattr("app.services.ai._gemini_weekly_summary", _fake_gemini)
    
    r = client.get(
        "/insights/weekly-summary",
        headers={
            **auth_header,
            "X-Gemini-Api-Key": "user-supplied-key",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "gemini"
    assert captured["api_key"] == "user-supplied-key"


def test_weekly_summary_falls_back_when_gemini_fails(client, auth_header, monkeypatch):
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
    assert "warnings" in payload
    assert "gemini_unavailable" in payload["warnings"]


def test_weekly_summary_with_income(client, auth_header):
    today = date.today()
    year, week_num, _ = today.isocalendar()
    current_week = f"{year}-W{week_num:02d}"
    
    # Add income
    r = client.post(
        "/expenses",
        json={
            "amount": 1000,
            "description": "Salary",
            "date": today.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    # Add expense
    r = client.post(
        "/expenses",
        json={
            "amount": 600,
            "description": "Rent",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    
    r = client.get(f"/insights/weekly-summary?week={current_week}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    assert payload["total_income"] == 1000.0
    assert payload["total_expenses"] == 600.0
    assert payload["net_flow"] == 400.0
    
    # Should include savings rate insight
    savings_insight = [i for i in payload["insights"] if "savings rate" in i.lower()]
    assert len(savings_insight) > 0
