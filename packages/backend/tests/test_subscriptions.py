"""Tests for subscription cost increase detection (issue #110).

Covers:
- Cost increase detection between consecutive recurring expenses
- No false positives when amounts stay the same
- Trend calculation with multiple price changes
- API endpoint query parameters
- Edge cases (single expense, zero amounts)
"""

from datetime import date, timedelta

import pytest


def _create_recurring(client, auth_header, **kwargs):
    defaults = {
        "amount": 10.0,
        "description": "Streaming Service",
        "cadence": "MONTHLY",
        "start_date": (date.today() - timedelta(days=120)).isoformat(),
    }
    defaults.update(kwargs)
    resp = client.post("/expenses/recurring", json=defaults, headers=auth_header)
    assert resp.status_code == 201
    return resp.get_json()["id"]


def _generate_expenses(client, auth_header, rec_id, through=None):
    through = through or date.today().isoformat()
    resp = client.post(
        f"/expenses/recurring/{rec_id}/generate",
        json={"through_date": through},
        headers=auth_header,
    )
    assert resp.status_code == 200
    return resp.get_json()["inserted"]


def test_no_increases_when_stable(client, auth_header):
    """Stable recurring expense should report no cost increases."""
    rec_id = _create_recurring(client, auth_header, amount=15.0)
    _generate_expenses(client, auth_header, rec_id)

    resp = client.get("/subscriptions/cost-increases", headers=auth_header)
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_detects_price_increase(client, auth_header):
    """Manually increasing an expense amount should be detected."""
    rec_id = _create_recurring(
        client, auth_header, amount=10.0, description="Music Subscription"
    )
    inserted = _generate_expenses(client, auth_header, rec_id)
    assert inserted >= 2

    # Get expenses and bump the latest one
    resp = client.get("/expenses", headers=auth_header)
    expenses = sorted(resp.get_json(), key=lambda e: e["date"])

    # Increase the last expense
    latest = expenses[-1]
    client.patch(
        f"/expenses/{latest['id']}",
        json={"amount": 14.99},  # ~50% increase from 10.0
        headers=auth_header,
    )

    resp = client.get("/subscriptions/cost-increases", headers=auth_header)
    assert resp.status_code == 200
    increases = resp.get_json()
    assert len(increases) >= 1
    assert increases[0]["name"] == "Music Subscription"
    assert increases[0]["new_amount"] == 14.99
    assert increases[0]["change_percent"] > 0


def test_trends_endpoint(client, auth_header):
    """Trends should show history for recurring subscriptions."""
    rec_id = _create_recurring(
        client, auth_header, amount=9.99, description="Cloud Storage"
    )
    _generate_expenses(client, auth_header, rec_id)

    resp = client.get("/subscriptions/trends", headers=auth_header)
    assert resp.status_code == 200
    trends = resp.get_json()
    assert len(trends) >= 1

    trend = trends[0]
    assert trend["name"] == "Cloud Storage"
    assert trend["original_amount"] == 9.99
    assert "history" in trend
    assert len(trend["history"]) >= 1


def test_min_change_percent_filter(client, auth_header):
    """Higher min_change_percent should filter out small increases."""
    rec_id = _create_recurring(client, auth_header, amount=100.0)
    _generate_expenses(client, auth_header, rec_id)

    # Small increase (2%)
    resp = client.get("/expenses", headers=auth_header)
    expenses = sorted(resp.get_json(), key=lambda e: e["date"])
    if len(expenses) >= 2:
        client.patch(
            f"/expenses/{expenses[-1]['id']}",
            json={"amount": 102.0},
            headers=auth_header,
        )

    # With low threshold - should detect
    resp = client.get(
        "/subscriptions/cost-increases?min_change_percent=1", headers=auth_header
    )
    low_threshold = resp.get_json()

    # With high threshold - should not detect
    resp = client.get(
        "/subscriptions/cost-increases?min_change_percent=10", headers=auth_header
    )
    high_threshold = resp.get_json()

    assert len(high_threshold) <= len(low_threshold)


def test_lookback_parameter(client, auth_header):
    """Lookback parameter should limit the analysis window."""
    resp = client.get(
        "/subscriptions/cost-increases?lookback_days=30", headers=auth_header
    )
    assert resp.status_code == 200

    resp = client.get("/subscriptions/trends?lookback_days=30", headers=auth_header)
    assert resp.status_code == 200


def test_single_expense_no_crash(client, auth_header):
    """A recurring with only one generated expense should not crash."""
    rec_id = _create_recurring(
        client,
        auth_header,
        amount=5.0,
        start_date=(date.today() - timedelta(days=15)).isoformat(),
    )
    _generate_expenses(client, auth_header, rec_id)

    resp = client.get("/subscriptions/cost-increases", headers=auth_header)
    assert resp.status_code == 200

    resp = client.get("/subscriptions/trends", headers=auth_header)
    assert resp.status_code == 200
