import json
from datetime import date, timedelta


def test_weekly_digest_returns_200(client, auth_headers, sample_expenses):
    """Weekly digest endpoint should return 200 with expected structure."""
    resp = client.get("/api/digest/weekly", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "period" in data
    assert "summary" in data
    assert "weekly_breakdown" in data
    assert "top_categories" in data
    assert "upcoming_bills" in data
    assert data["period"]["weeks"] == 4


def test_weekly_digest_custom_weeks(client, auth_headers, sample_expenses):
    """Weekly digest should respect the weeks query parameter."""
    resp = client.get("/api/digest/weekly?weeks=8", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["period"]["weeks"] == 8
    assert len(data["weekly_breakdown"]) == 8


def test_weekly_digest_weeks_out_of_range(client, auth_headers):
    """Weekly digest should clamp weeks to 1-12 range or reject."""
    resp = client.get("/api/digest/weekly?weeks=0", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["period"]["weeks"] == 1


def test_weekly_digest_unauthorized(client):
    """Weekly digest should reject unauthenticated requests."""
    resp = client.get("/api/digest/weekly")
    assert resp.status_code == 401


def test_weekly_digest_wow_delta(client, auth_headers, sample_expenses):
    """First week should have null delta, subsequent weeks should have computed deltas."""
    resp = client.get("/api/digest/weekly?weeks=4", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    breakdown = data["weekly_breakdown"]
    assert breakdown[0]["wow_delta"] is None
    assert breakdown[0]["trend"] == "flat"
    # Subsequent weeks should have delta info
    if len(breakdown) > 1:
        assert breakdown[1]["wow_delta"] is not None
        assert breakdown[1]["trend"] in ("up", "down", "flat")


def test_weekly_digest_top_categories(client, auth_headers, sample_expenses):
    """Top categories should be returned sorted by amount."""
    resp = client.get("/api/digest/weekly", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    cats = data["top_categories"]
    # Verify sorted descending
    amounts = [c["total"] for c in cats]
    assert amounts == sorted(amounts, reverse=True)
