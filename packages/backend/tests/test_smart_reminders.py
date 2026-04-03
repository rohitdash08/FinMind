"""Tests for smart reminder timing (issue #111)."""

from datetime import date, timedelta
import pytest


def test_timing_empty(client, auth_header):
    resp = client.get("/smart-reminders/timing", headers=auth_header)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "optimal_day_of_week" in data
    assert data["confidence"] == "low"


def test_timing_with_data(client, auth_header):
    today = date.today()
    for i in range(20):
        d = today - timedelta(days=i * 3)
        client.post("/expenses", json={
            "amount": 10, "description": "Daily", "date": d.isoformat()
        }, headers=auth_header)

    resp = client.get("/smart-reminders/timing", headers=auth_header)
    data = resp.get_json()
    assert data["confidence"] in ("low", "medium", "high")
    assert sum(data["activity_by_day"].values()) >= 1


def test_suggest_reminder(client, auth_header):
    due = (date.today() + timedelta(days=14)).isoformat()
    resp = client.get(f"/smart-reminders/suggest?due_date={due}", headers=auth_header)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["due_date"] == due
    assert data["suggested_reminder"] <= due


def test_suggest_missing_date(client, auth_header):
    resp = client.get("/smart-reminders/suggest", headers=auth_header)
    assert resp.status_code == 400
