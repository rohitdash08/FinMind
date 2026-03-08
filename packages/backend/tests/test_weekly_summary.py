"""Tests for the weekly financial digest endpoint."""

from datetime import date, timedelta


def test_weekly_summary_returns_structure(client, auth_header):
    r = client.get("/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "week" in data
    assert "start" in data["week"]
    assert "end" in data["week"]
    assert "totals" in data
    assert "daily_breakdown" in data
    assert "category_breakdown" in data
    assert "top_expenses" in data
    assert "upcoming_bills" in data
    assert "trends" in data
    # Daily breakdown always has 7 days
    assert len(data["daily_breakdown"]) == 7


def test_weekly_summary_with_expenses(client, auth_header):
    today = date.today()
    # Create an expense for today
    client.post(
        "/expenses",
        json={
            "amount": 42.50,
            "description": "Groceries",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    # Create an income for today
    client.post(
        "/expenses",
        json={
            "amount": 1000,
            "description": "Salary",
            "date": today.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )

    r = client.get("/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["totals"]["expenses"] == 42.50
    assert data["totals"]["income"] == 1000.0
    assert data["totals"]["net"] == 957.50
    assert data["totals"]["transaction_count"] == 2
    assert len(data["top_expenses"]) == 1
    assert data["top_expenses"][0]["description"] == "Groceries"


def test_weekly_summary_specific_week(client, auth_header):
    # Query a past week
    past = (date.today() - timedelta(days=14)).isoformat()
    r = client.get(f"/weekly-summary?week_of={past}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["totals"]["transaction_count"] == 0


def test_weekly_summary_invalid_date(client, auth_header):
    r = client.get("/weekly-summary?week_of=not-a-date", headers=auth_header)
    assert r.status_code == 400
    assert "invalid" in r.get_json()["error"].lower()


def test_weekly_summary_requires_auth(client):
    r = client.get("/weekly-summary")
    assert r.status_code == 401


def test_weekly_summary_trends(client, auth_header):
    today = date.today()
    last_week = today - timedelta(days=7)
    # Expense last week
    client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Last week item",
            "date": last_week.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    # Expense this week
    client.post(
        "/expenses",
        json={
            "amount": 150,
            "description": "This week item",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    r = client.get("/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    trends = data["trends"]
    assert trends["previous_week_expenses"] == 100.0
    # Expense change should be +50%
    assert trends["expense_change_pct"] == 50.0


def test_weekly_summary_with_bills(client, auth_header):
    today = date.today()
    # Create a bill due this week
    monday = today - timedelta(days=today.weekday())
    due = monday + timedelta(days=3)
    client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 59.99,
            "next_due_date": due.isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )

    r = client.get("/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["upcoming_bills"]) >= 1
    assert data["upcoming_bills"][0]["name"] == "Internet"
