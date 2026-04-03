"""Tests for transaction deduplication (issue #113)."""

from datetime import date, timedelta
import pytest


def _add(client, auth_header, amount, desc, d):
    resp = client.post("/expenses", json={"amount": amount, "description": desc, "date": d}, headers=auth_header)
    assert resp.status_code == 201
    return resp.get_json()["id"]


def test_no_duplicates(client, auth_header):
    _add(client, auth_header, 10, "Coffee", date.today().isoformat())
    _add(client, auth_header, 20, "Lunch", date.today().isoformat())
    resp = client.get("/duplicates", headers=auth_header)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 0


def test_exact_duplicate(client, auth_header):
    d = date.today().isoformat()
    _add(client, auth_header, 15.50, "Starbucks", d)
    _add(client, auth_header, 15.50, "Starbucks", d)
    resp = client.get("/duplicates", headers=auth_header)
    dupes = resp.get_json()
    assert len(dupes) >= 1
    assert dupes[0]["match_type"] == "exact"
    assert dupes[0]["confidence"] == 100


def test_near_duplicate(client, auth_header):
    d = date.today().isoformat()
    _add(client, auth_header, 25, "Coffee at Starbucks", d)
    _add(client, auth_header, 25, "Starbucks coffee", d)
    resp = client.get("/duplicates", headers=auth_header)
    dupes = resp.get_json()
    near = [d for d in dupes if d["match_type"] == "near"]
    assert len(near) >= 1


def test_temporal_duplicate(client, auth_header):
    d1 = date.today().isoformat()
    d2 = (date.today() - timedelta(days=1)).isoformat()
    _add(client, auth_header, 50, "Electricity bill", d1)
    _add(client, auth_header, 50, "Electricity bill", d2)
    resp = client.get("/duplicates", headers=auth_header)
    dupes = resp.get_json()
    temporal = [d for d in dupes if d["match_type"] == "temporal"]
    assert len(temporal) >= 1


def test_merge(client, auth_header):
    d = date.today().isoformat()
    id1 = _add(client, auth_header, 30, "Duplicate", d)
    id2 = _add(client, auth_header, 30, "Duplicate", d)
    resp = client.post("/duplicates/merge", json={"keep_id": id1, "remove_id": id2}, headers=auth_header)
    assert resp.status_code == 200

    # Verify removed
    expenses = client.get("/expenses", headers=auth_header).get_json()
    ids = [e["id"] for e in expenses]
    assert id1 in ids
    assert id2 not in ids


def test_confidence_filter(client, auth_header):
    resp = client.get("/duplicates?min_confidence=90", headers=auth_header)
    assert resp.status_code == 200
    for d in resp.get_json():
        assert d["confidence"] >= 90
