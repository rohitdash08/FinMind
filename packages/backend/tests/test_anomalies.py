"""Tests for recurring transaction anomaly detection (issue #108).

Covers:
- Amount change detection
- Missing transaction detection
- Recurring pattern detection from non-recurring expenses
- API endpoint filtering (severity, type, lookback)
- Summary endpoint
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest


def _create_recurring(client, auth_header, **kwargs):
    """Helper to create a recurring expense and return its ID."""
    defaults = {
        "amount": 100.0,
        "description": "Monthly Subscription",
        "cadence": "MONTHLY",
        "start_date": (date.today() - timedelta(days=90)).isoformat(),
    }
    defaults.update(kwargs)
    resp = client.post("/expenses/recurring", json=defaults, headers=auth_header)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["id"]


def _generate_recurring(client, auth_header, recurring_id, through_date=None):
    """Generate expenses from a recurring definition."""
    through = through_date or date.today().isoformat()
    resp = client.post(
        f"/expenses/recurring/{recurring_id}/generate",
        json={"through_date": through},
        headers=auth_header,
    )
    assert resp.status_code == 200
    return resp.get_json()["inserted"]


def test_anomaly_endpoint_empty(client, auth_header):
    """No recurring expenses → no anomalies."""
    resp = client.get("/anomalies", headers=auth_header)
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_anomaly_summary_empty(client, auth_header):
    """Summary with no anomalies."""
    resp = client.get("/anomalies/summary", headers=auth_header)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 0


def test_amount_anomaly_detected(client, auth_header):
    """Modifying a generated expense amount should trigger an amount_change anomaly."""
    rec_id = _create_recurring(
        client,
        auth_header,
        amount=50.0,
        description="Gym Membership",
        start_date=(date.today() - timedelta(days=60)).isoformat(),
    )
    inserted = _generate_recurring(client, auth_header, rec_id)
    assert inserted >= 1

    # Get expenses and modify one's amount directly
    resp = client.get("/expenses", headers=auth_header)
    expenses = resp.get_json()
    assert len(expenses) >= 1

    # Patch the first expense to a different amount
    target = expenses[0]
    patch_resp = client.patch(
        f"/expenses/{target['id']}",
        json={"amount": 75.0},  # 50% increase
        headers=auth_header,
    )
    assert patch_resp.status_code == 200

    # Now check anomalies
    resp = client.get("/anomalies", headers=auth_header)
    assert resp.status_code == 200
    anomalies = resp.get_json()

    amount_anomalies = [a for a in anomalies if a["type"] == "amount_change"]
    assert len(amount_anomalies) >= 1
    assert amount_anomalies[0]["severity"] == "high"  # 50% change


def test_missing_transaction_detected(client, auth_header):
    """A recurring expense with no generated expenses should flag missing transactions."""
    # Create a weekly recurring that started 30 days ago
    rec_id = _create_recurring(
        client,
        auth_header,
        amount=20.0,
        description="Weekly Coffee",
        cadence="WEEKLY",
        start_date=(date.today() - timedelta(days=30)).isoformat(),
    )
    # Don't generate any expenses — they're all "missing"

    resp = client.get("/anomalies", headers=auth_header)
    anomalies = resp.get_json()
    missing = [a for a in anomalies if a["type"] == "missing_transaction"]
    # Should have at least some missing transactions
    assert len(missing) >= 1


def test_severity_filter(client, auth_header):
    """Filtering by severity should narrow results."""
    resp = client.get("/anomalies?severity=high", headers=auth_header)
    assert resp.status_code == 200
    for a in resp.get_json():
        assert a["severity"] == "high"


def test_type_filter(client, auth_header):
    """Filtering by type should narrow results."""
    resp = client.get("/anomalies?type=amount_change", headers=auth_header)
    assert resp.status_code == 200
    for a in resp.get_json():
        assert a["type"] == "amount_change"


def test_lookback_parameter(client, auth_header):
    """Custom lookback_days parameter should be respected."""
    resp = client.get("/anomalies?lookback_days=7", headers=auth_header)
    assert resp.status_code == 200

    resp = client.get("/anomalies?lookback_days=invalid", headers=auth_header)
    assert resp.status_code == 200  # falls back to default


def test_recurring_pattern_detection(client, auth_header):
    """Expenses with same description and regular intervals should be flagged."""
    # Create 4 expenses with same description, monthly-ish intervals
    base = date.today() - timedelta(days=90)
    for i in range(4):
        d = base + timedelta(days=30 * i)
        client.post(
            "/expenses",
            json={
                "amount": 9.99,
                "description": "Netflix",
                "date": d.isoformat(),
            },
            headers=auth_header,
        )

    resp = client.get("/anomalies", headers=auth_header)
    anomalies = resp.get_json()
    patterns = [a for a in anomalies if a["type"] == "recurring_pattern_detected"]
    assert len(patterns) >= 1
    assert "Netflix" in patterns[0]["description"]


def test_anomaly_summary_counts(client, auth_header):
    """Summary should group anomalies by type and severity."""
    # Create a recurring with missing transactions
    _create_recurring(
        client,
        auth_header,
        amount=30.0,
        description="Weekly Groceries",
        cadence="WEEKLY",
        start_date=(date.today() - timedelta(days=28)).isoformat(),
    )

    resp = client.get("/anomalies/summary", headers=auth_header)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "total" in data
    assert "by_type" in data
    assert "by_severity" in data
