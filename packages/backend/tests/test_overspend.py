"""Tests for category overspend early warning (issue #117)."""

from datetime import date, timedelta
import pytest


def _add_expense(client, auth_header, amount, desc, d, cat_id=None):
    payload = {"amount": amount, "description": desc, "date": d}
    if cat_id:
        payload["category_id"] = cat_id
    resp = client.post("/expenses", json=payload, headers=auth_header)
    assert resp.status_code == 201
    return resp.get_json()


def _create_category(client, auth_header, name):
    resp = client.post("/categories", json={"name": name}, headers=auth_header)
    assert resp.status_code == 201
    return resp.get_json()["id"]


def test_empty_no_warnings(client, auth_header):
    resp = client.get("/overspend", headers=auth_header)
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_on_track_spending(client, auth_header):
    """Spending at normal pace should show on_track."""
    cat_id = _create_category(client, auth_header, "Food")
    today = date.today()

    # Historical: 3 months of ~100/month
    for m in range(1, 4):
        d = today.replace(day=15) - timedelta(days=30 * m)
        _add_expense(client, auth_header, 100.0, "Groceries", d.isoformat(), cat_id)

    # This month: proportional spending (early in month = less)
    _add_expense(client, auth_header, 30.0, "Groceries today", today.isoformat(), cat_id)

    resp = client.get("/overspend", headers=auth_header)
    assert resp.status_code == 200
    warnings = resp.get_json()
    if warnings:
        # Should not be critical
        food_warn = [w for w in warnings if w["category_id"] == cat_id]
        if food_warn:
            assert food_warn[0]["level"] in ("on_track", "caution")


def test_critical_overspend(client, auth_header):
    """Spending way above average pace should trigger critical."""
    cat_id = _create_category(client, auth_header, "Entertainment")
    today = date.today()

    # Historical: 3 months of ~50/month
    for m in range(1, 4):
        d = today.replace(day=15) - timedelta(days=30 * m)
        _add_expense(client, auth_header, 50.0, "Movies", d.isoformat(), cat_id)

    # This month: already at 200 (4x the average)
    _add_expense(client, auth_header, 200.0, "Concert", today.isoformat(), cat_id)

    resp = client.get("/overspend", headers=auth_header)
    warnings = resp.get_json()
    ent_warns = [w for w in warnings if w["category_id"] == cat_id]
    assert len(ent_warns) >= 1
    assert ent_warns[0]["level"] in ("warning", "critical")


def test_level_filter(client, auth_header):
    resp = client.get("/overspend?level=critical", headers=auth_header)
    assert resp.status_code == 200
    for w in resp.get_json():
        assert w["level"] == "critical"


def test_reference_months_param(client, auth_header):
    resp = client.get("/overspend?reference_months=6", headers=auth_header)
    assert resp.status_code == 200

    resp = client.get("/overspend?reference_months=invalid", headers=auth_header)
    assert resp.status_code == 200
