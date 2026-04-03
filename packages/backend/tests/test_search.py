"""Tests for unified search (issue #105)."""

from datetime import date, timedelta
import pytest


def _seed(client, auth_header):
    """Create test data across expenses, bills."""
    for i in range(5):
        client.post("/expenses", json={
            "amount": 10 + i * 10,
            "description": f"Coffee shop visit {i}",
            "date": (date.today() - timedelta(days=i * 7)).isoformat(),
        }, headers=auth_header)

    client.post("/expenses", json={
        "amount": 500,
        "description": "Laptop repair",
        "date": date.today().isoformat(),
    }, headers=auth_header)

    client.post("/bills", json={
        "name": "Netflix subscription",
        "amount": 15.99,
        "next_due_date": (date.today() + timedelta(days=10)).isoformat(),
        "cadence": "MONTHLY",
    }, headers=auth_header)


def test_search_empty_query(client, auth_header):
    resp = client.get("/search", headers=auth_header)
    assert resp.status_code == 200
    assert "results" in resp.get_json()


def test_search_by_text(client, auth_header):
    _seed(client, auth_header)
    resp = client.get("/search?q=coffee", headers=auth_header)
    data = resp.get_json()
    assert data["total"] >= 1
    for r in data["results"]:
        assert "coffee" in r["description"].lower()


def test_search_by_type_expense(client, auth_header):
    _seed(client, auth_header)
    resp = client.get("/search?type=expense", headers=auth_header)
    for r in resp.get_json()["results"]:
        assert r["type"] == "expense"


def test_search_by_type_bill(client, auth_header):
    _seed(client, auth_header)
    resp = client.get("/search?q=netflix&type=bill", headers=auth_header)
    data = resp.get_json()
    assert data["total"] >= 1
    assert data["results"][0]["type"] == "bill"


def test_search_amount_range(client, auth_header):
    _seed(client, auth_header)
    resp = client.get("/search?min_amount=100&max_amount=600", headers=auth_header)
    for r in resp.get_json()["results"]:
        if r["amount"] is not None:
            assert 100 <= r["amount"] <= 600


def test_search_date_range(client, auth_header):
    _seed(client, auth_header)
    today = date.today().isoformat()
    resp = client.get(f"/search?from_date={today}&to_date={today}&type=expense", headers=auth_header)
    assert resp.status_code == 200


def test_search_sort_by_amount(client, auth_header):
    _seed(client, auth_header)
    resp = client.get("/search?type=expense&sort=amount", headers=auth_header)
    results = resp.get_json()["results"]
    amounts = [r["amount"] for r in results if r["amount"]]
    assert amounts == sorted(amounts, reverse=True)
