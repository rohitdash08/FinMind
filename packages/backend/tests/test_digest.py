"""Tests for weekly financial digest feature."""

from datetime import date, timedelta
from unittest.mock import patch


# Helper


def _seed_expenses(client, auth_header, items):
    """Create expense records via the API."""
    for item in items:
        r = client.post("/expenses", json=item, headers=auth_header)
        assert r.status_code == 201, f"seed failed: {r.get_json()}"


def _last_monday():
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    return current_monday - timedelta(days=7)


# GET /digest/weekly


def test_weekly_digest_returns_summary(client, auth_header):
    """Digest should contain summary, category_breakdown, highlights."""
    monday = _last_monday()
    wednesday = monday + timedelta(days=2)

    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 500,
                "description": "Groceries",
                "date": wednesday.isoformat(),
                "expense_type": "EXPENSE",
            },
            {
                "amount": 3000,
                "description": "Salary",
                "date": monday.isoformat(),
                "expense_type": "INCOME",
            },
        ],
    )

    r = client.get(
        f"/digest/weekly?week_start={monday.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()

    assert "payload" in data
    payload = data["payload"]
    assert "summary" in payload
    assert payload["summary"]["total_expenses"] >= 500
    assert payload["summary"]["total_income"] >= 3000
    assert payload["summary"]["net_flow"] >= 2500
    assert "category_breakdown" in payload
    assert "highlights" in payload
    assert "ai_insight" in data


def test_weekly_digest_empty_week(client, auth_header):
    """Digest for a week with no data should return zeroed summary."""
    far_past = date(2020, 1, 6)  # a Monday
    r = client.get(
        f"/digest/weekly?week_start={far_past.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    payload = data["payload"]
    assert payload["summary"]["total_expenses"] == 0
    assert payload["summary"]["total_income"] == 0
    assert payload["summary"]["net_flow"] == 0
    assert payload["summary"]["transaction_count"] == 0


def test_weekly_digest_invalid_week_start(client, auth_header):
    r = client.get(
        "/digest/weekly?week_start=not-a-date",
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "invalid" in r.get_json()["error"].lower()


# Idempotency


def test_weekly_digest_idempotent(client, auth_header, app_fixture):
    """Calling twice for same week should not create duplicate DB rows."""
    monday = _last_monday()

    _seed_expenses(
        client,
        auth_header,
        [
            {
                "amount": 100,
                "description": "Test",
                "date": monday.isoformat(),
                "expense_type": "EXPENSE",
            },
        ],
    )

    r1 = client.get(
        f"/digest/weekly?week_start={monday.isoformat()}",
        headers=auth_header,
    )
    assert r1.status_code == 200
    id1 = r1.get_json()["id"]

    r2 = client.get(
        f"/digest/weekly?week_start={monday.isoformat()}",
        headers=auth_header,
    )
    assert r2.status_code == 200
    id2 = r2.get_json()["id"]

    assert id1 == id2, "Digest should be idempotent for same week"


# GET /digest/weekly/history


def test_weekly_digest_history(client, auth_header):
    """History endpoint should return a list of past digests."""
    monday = _last_monday()

    # Generate a digest first
    client.get(
        f"/digest/weekly?week_start={monday.isoformat()}",
        headers=auth_header,
    )

    r = client.get("/digest/weekly/history", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    item = data[0]
    assert "week_start" in item
    assert "week_end" in item
    assert "total_expenses" in item
    assert "net_flow" in item


def test_weekly_digest_history_respects_limit(client, auth_header):
    r = client.get("/digest/weekly/history?limit=1", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) <= 1


# POST /digest/weekly/send


def test_weekly_digest_send_triggers_email(client, auth_header):
    """Send endpoint should attempt email delivery."""
    with patch("app.services.digest.send_email", return_value=True) as mock_send:
        r = client.post("/digest/weekly/send", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["sent"] is True
        assert "digest_id" in data
        assert mock_send.called


def test_weekly_digest_send_handles_email_failure(client, auth_header):
    """Send endpoint should handle email failure gracefully."""
    with patch("app.services.digest.send_email", return_value=False):
        r = client.post("/digest/weekly/send", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["sent"] is False


# AI insight


def test_weekly_digest_ai_insight_with_gemini(client, auth_header, monkeypatch):
    """When Gemini is available, method should be gemini."""
    monday = date(2020, 6, 1)  # unique week to avoid cache

    def _fake_gemini(payload, key, model, persona):
        return "Great week! Your spending is on track.", "gemini"

    monkeypatch.setattr("app.services.digest._gemini_insight", _fake_gemini)
    monkeypatch.setattr("app.services.digest._settings.gemini_api_key", "test-key")

    r = client.get(
        f"/digest/weekly?week_start={monday.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["method"] == "gemini"
    assert "Great week" in data["ai_insight"]


def test_weekly_digest_falls_back_to_heuristic(client, auth_header, monkeypatch):
    """When Gemini fails, should fall back to heuristic."""
    monday = date(2020, 7, 6)  # unique week

    def _boom(*args, **kwargs):
        raise RuntimeError("gemini down")

    monkeypatch.setattr("app.services.digest._gemini_insight", _boom)
    monkeypatch.setattr("app.services.digest._settings.gemini_api_key", "test-key")

    r = client.get(
        f"/digest/weekly?week_start={monday.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["method"] == "heuristic"
    assert data["ai_insight"]  # should not be empty


# Auth


def test_weekly_digest_requires_auth(client):
    """Endpoints should reject unauthenticated requests."""
    assert client.get("/digest/weekly").status_code == 401
    assert client.get("/digest/weekly/history").status_code == 401
    assert client.post("/digest/weekly/send").status_code == 401


# week_boundaries helper


def test_week_boundaries_returns_monday_to_sunday():
    from app.services.digest import week_boundaries

    # Test with a known Wednesday: 2026-03-11
    start, end = week_boundaries(date(2026, 3, 11))

    # Should return previous completed week: Mon Mar 2 – Sun Mar 8
    assert start.weekday() == 0, "week_start should be Monday"
    assert end.weekday() == 6, "week_end should be Sunday"
    assert (end - start).days == 6
    assert start == date(2026, 3, 2)
    assert end == date(2026, 3, 8)


def test_week_boundaries_on_monday():
    from app.services.digest import week_boundaries

    # On a Monday, should still return the *previous* week
    start, end = week_boundaries(date(2026, 3, 9))  # Monday
    assert start == date(2026, 3, 2)
    assert end == date(2026, 3, 8)
