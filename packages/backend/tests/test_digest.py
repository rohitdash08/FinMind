"""Tests for the weekly financial digest endpoint."""
from datetime import date, timedelta


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def test_weekly_digest_returns_required_fields(client, auth_header):
    """GET /insights/weekly-digest returns all required response keys."""
    today = date.today()
    monday = _monday_of(today)

    # Add an expense in the current week
    r = client.post(
        "/expenses",
        json={
            "amount": 120,
            "description": "Groceries",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    required_keys = {
        "week_start",
        "week_end",
        "total_expenses",
        "total_income",
        "net_flow",
        "week_over_week_change_pct",
        "previous_week_expenses",
        "top_categories",
        "daily_breakdown",
        "insights",
        "method",
    }
    assert required_keys.issubset(payload.keys()), (
        f"Missing keys: {required_keys - payload.keys()}"
    )
    assert payload["method"] == "heuristic"
    assert payload["total_expenses"] >= 120


def test_weekly_digest_week_param(client, auth_header):
    """Passing ?week= selects a specific week."""
    target_monday = _monday_of(date.today()) - timedelta(weeks=2)

    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Old week spend",
            "date": target_monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        f"/insights/weekly-digest?week={target_monday.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["week_start"] == str(target_monday)
    assert payload["total_expenses"] >= 50


def test_weekly_digest_invalid_week_param(client, auth_header):
    """Invalid ?week= returns 400."""
    r = client.get("/insights/weekly-digest?week=not-a-date", headers=auth_header)
    assert r.status_code == 400


def test_weekly_digest_net_flow(client, auth_header):
    """net_flow is income - expenses."""
    today = date.today()
    monday = _monday_of(today)

    client.post(
        "/expenses",
        json={"amount": 200, "description": "Salary", "date": monday.isoformat(), "expense_type": "INCOME"},
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={"amount": 80, "description": "Lunch", "date": monday.isoformat(), "expense_type": "EXPENSE"},
        headers=auth_header,
    )

    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert abs(payload["net_flow"] - (payload["total_income"] - payload["total_expenses"])) < 0.01


def test_weekly_digest_uses_gemini_key(client, auth_header, monkeypatch):
    """When X-Gemini-Api-Key is supplied, _gemini_digest is called."""
    captured = {}

    def _fake(uid, start, end, prev_start, prev_end, api_key, model, persona):
        captured["api_key"] = api_key
        return {
            "week_start": str(start),
            "week_end": str(end),
            "total_expenses": 0.0,
            "total_income": 0.0,
            "net_flow": 0.0,
            "week_over_week_change_pct": 0.0,
            "previous_week_expenses": 0.0,
            "top_categories": [],
            "daily_breakdown": [],
            "insights": ["AI tip"],
            "method": "gemini",
        }

    monkeypatch.setattr("app.services.digest._gemini_digest", _fake)

    r = client.get(
        "/insights/weekly-digest",
        headers={**auth_header, "X-Gemini-Api-Key": "test-key"},
    )
    assert r.status_code == 200
    assert r.get_json()["method"] == "gemini"
    assert captured["api_key"] == "test-key"


def test_weekly_digest_falls_back_on_gemini_error(client, auth_header, monkeypatch):
    """When Gemini fails, falls back to heuristic with warning."""
    def _boom(*_args, **_kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr("app.services.digest._gemini_digest", _boom)

    r = client.get(
        "/insights/weekly-digest",
        headers={**auth_header, "X-Gemini-Api-Key": "bad-key"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "heuristic"
    assert "warnings" in payload
    assert "gemini_unavailable" in payload["warnings"]
