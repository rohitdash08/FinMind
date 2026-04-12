from datetime import date, timedelta


def _iso_week_str(d):
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def test_weekly_digest_returns_expected_fields(client, auth_header):
    today = date.today()
    week_str = _iso_week_str(today)

    # Add an expense in the current week
    r = client.post(
        "/expenses",
        json={
            "amount": 75,
            "description": "Weekly test spend",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(f"/digest/weekly?week={week_str}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["week"] == week_str
    assert "total_income" in payload
    assert "total_expenses" in payload
    assert "net_flow" in payload
    assert "analytics" in payload
    assert "week_over_week_change_pct" in payload["analytics"]
    assert "tips" in payload
    assert payload["method"] == "heuristic"


def test_weekly_digest_defaults_to_current_week(client, auth_header):
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    expected = _iso_week_str(date.today())
    assert payload["week"] == expected


def test_weekly_digest_rejects_invalid_week_format(client, auth_header):
    r = client.get("/digest/weekly?week=2026-13", headers=auth_header)
    assert r.status_code == 400

    r = client.get("/digest/weekly?week=not-a-week", headers=auth_header)
    assert r.status_code == 400


def test_weekly_digest_requires_auth(client):
    r = client.get("/digest/weekly")
    assert r.status_code == 401


def test_weekly_digest_gemini_fallback(client, auth_header, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("gemini down")

    monkeypatch.setattr("app.services.ai._gemini_weekly_digest", _boom)

    r = client.get(
        "/digest/weekly",
        headers={
            **auth_header,
            "X-Gemini-Api-Key": "user-key",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "heuristic"
    assert "warnings" in payload
    assert "gemini_unavailable" in payload["warnings"]


def test_weekly_digest_week_over_week(client, auth_header):
    today = date.today()
    last_week = today - timedelta(weeks=1)

    # Expense this week
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "This week",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Expense last week
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Last week",
            "date": last_week.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    week_str = _iso_week_str(today)
    r = client.get(f"/digest/weekly?week={week_str}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["analytics"]["week_over_week_change_pct"] != 0
