"""Tests for expense and bill export endpoints (CSV and JSON)."""

import csv
import io
import json
from datetime import date


def test_expense_export_csv(client, auth_header):
    # Create expenses
    client.post(
        "/expenses",
        json={
            "amount": 42.50,
            "description": "Lunch",
            "date": "2026-03-15",
            "currency": "USD",
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 15.00,
            "description": "Coffee",
            "date": "2026-03-16",
            "currency": "USD",
        },
        headers=auth_header,
    )

    r = client.get("/expenses/export?format=csv", headers=auth_header)
    assert r.status_code == 200
    assert r.content_type == "text/csv; charset=utf-8"
    assert "attachment" in r.headers.get("Content-Disposition", "")

    # Parse CSV
    reader = csv.reader(io.StringIO(r.data.decode("utf-8")))
    rows = list(reader)
    assert rows[0] == ["date", "amount", "currency", "category", "type", "notes"]
    assert len(rows) == 3  # header + 2 expenses
    # Most recent first
    assert rows[1][5] == "Coffee"
    assert rows[2][5] == "Lunch"


def test_expense_export_json(client, auth_header):
    client.post(
        "/expenses",
        json={
            "amount": 99.99,
            "description": "Gadget",
            "date": "2026-03-10",
            "currency": "EUR",
        },
        headers=auth_header,
    )

    r = client.get("/expenses/export?format=json", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["amount"] == 99.99
    assert data[0]["notes"] == "Gadget"
    assert data[0]["currency"] == "EUR"


def test_expense_export_date_filter(client, auth_header):
    client.post(
        "/expenses",
        json={"amount": 10, "description": "Jan", "date": "2026-01-15"},
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={"amount": 20, "description": "Mar", "date": "2026-03-15"},
        headers=auth_header,
    )

    # Filter to March only
    r = client.get(
        "/expenses/export?format=json&from=2026-03-01&to=2026-03-31",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 1
    assert data[0]["notes"] == "Mar"


def test_expense_export_empty(client, auth_header):
    r = client.get("/expenses/export?format=csv", headers=auth_header)
    assert r.status_code == 200
    reader = csv.reader(io.StringIO(r.data.decode("utf-8")))
    rows = list(reader)
    assert len(rows) == 1  # header only


def test_expense_export_invalid_format(client, auth_header):
    r = client.get("/expenses/export?format=xml", headers=auth_header)
    assert r.status_code == 400


def test_expense_export_auth_required(client):
    r = client.get("/expenses/export")
    assert r.status_code == 401


def test_bill_export_csv(client, auth_header):
    client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 49.99,
            "currency": "USD",
            "next_due_date": date.today().isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )

    r = client.get("/bills/export?format=csv", headers=auth_header)
    assert r.status_code == 200
    assert r.content_type == "text/csv; charset=utf-8"

    reader = csv.reader(io.StringIO(r.data.decode("utf-8")))
    rows = list(reader)
    assert rows[0] == ["name", "amount", "currency", "next_due_date", "cadence", "autopay"]
    assert len(rows) == 2
    assert rows[1][0] == "Internet"


def test_bill_export_json(client, auth_header):
    client.post(
        "/bills",
        json={
            "name": "Gym",
            "amount": 30.00,
            "next_due_date": date.today().isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )

    r = client.get("/bills/export?format=json", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "Gym"
    assert data[0]["cadence"] == "MONTHLY"


def test_bill_export_auth_required(client):
    r = client.get("/bills/export")
    assert r.status_code == 401
