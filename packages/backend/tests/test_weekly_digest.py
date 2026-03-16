from datetime import date, timedelta


def test_weekly_digest_returns_analytics_fields(client, auth_header):
    current = date.today()
    previous = current - timedelta(days=8)

    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Current week spend",
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
            "description": "Previous week spend",
            "date": previous.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    end_date = (current + timedelta(days=1)).isoformat()
    r = client.get(f"/insights/weekly-digest?end_date={end_date}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "analytics" in payload
    assert "week_over_week_change_pct" in payload["analytics"]
    assert payload["end_date"] == end_date


def test_weekly_digest_prefers_user_gemini_key(client, auth_header, monkeypatch):
    captured = {}

    def _fake_gemini(uid, end_date, api_key, model, persona):
        captured["uid"] = uid
        captured["end_date"] = end_date
        captured["api_key"] = api_key
        captured["model"] = model
        captured["persona"] = persona
        return {
            "summary": "Fake summary",
            "insights": ["Tip 1", "Tip 2"],
            "method": "gemini",
        }

    monkeypatch.setattr("app.services.ai._gemini_weekly_digest", _fake_gemini)

    r = client.get(
        "/insights/weekly-digest",
        headers={
            **auth_header,
            "X-Gemini-Api-Key": "user-supplied-key",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "gemini"
    assert payload["summary"] == "Fake summary"
    assert captured["api_key"] == "user-supplied-key"


def test_weekly_digest_falls_back_when_gemini_fails(
    client, auth_header, monkeypatch
):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("gemini down")

    monkeypatch.setattr("app.services.ai._gemini_weekly_digest", _boom)

    r = client.get(
        "/insights/weekly-digest",
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
