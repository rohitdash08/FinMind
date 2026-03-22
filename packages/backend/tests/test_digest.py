"""Tests for the weekly financial digest endpoint and service."""

from datetime import date, timedelta


def _create_expense(client, auth_header, amount, expense_date, expense_type="EXPENSE", description="Test"):
    """Helper to create an expense."""
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "description": description,
            "date": expense_date.isoformat(),
            "expense_type": expense_type,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r


def _last_monday():
    """Return the Monday of the previous full week."""
    today = date.today()
    days_since_monday = today.isoweekday() - 1
    this_monday = today - timedelta(days=days_since_monday)
    return this_monday - timedelta(weeks=1)


def test_weekly_digest_returns_structure(client, auth_header):
    """Digest endpoint returns all expected top-level keys."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert "period" in payload
    assert payload["period"]["type"] == "weekly"
    assert "start" in payload["period"]
    assert "end" in payload["period"]

    assert "summary" in payload
    summary = payload["summary"]
    assert "total_income" in summary
    assert "total_expenses" in summary
    assert "net_flow" in summary
    assert "transaction_count" in summary
    assert "week_over_week_change_pct" in summary
    assert "previous_week_expenses" in summary

    assert "category_breakdown" in payload
    assert "daily_spending" in payload
    assert "insights" in payload
    assert isinstance(payload["insights"], list)


def test_weekly_digest_reflects_expenses(client, auth_header):
    """Digest totals match expenses created in the previous week."""
    monday = _last_monday()
    wednesday = monday + timedelta(days=2)
    friday = monday + timedelta(days=4)

    _create_expense(client, auth_header, 100, monday, "EXPENSE", "Groceries")
    _create_expense(client, auth_header, 50, wednesday, "EXPENSE", "Transport")
    _create_expense(client, auth_header, 200, friday, "INCOME", "Salary")

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    summary = payload["summary"]
    assert summary["total_expenses"] == 150.0
    assert summary["total_income"] == 200.0
    assert summary["net_flow"] == 50.0
    assert summary["transaction_count"] == 2  # only expense transactions counted in categories


def test_weekly_digest_wow_change(client, auth_header):
    """Week-over-week change percentage is computed correctly."""
    monday = _last_monday()
    prev_monday = monday - timedelta(weeks=1)

    # Previous week: 100 in expenses
    _create_expense(client, auth_header, 100, prev_monday, "EXPENSE", "Prev week")
    # Current week: 150 in expenses (50% increase)
    _create_expense(client, auth_header, 150, monday, "EXPENSE", "Curr week")

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"]["week_over_week_change_pct"] == 50.0
    assert payload["summary"]["previous_week_expenses"] == 100.0


def test_weekly_digest_daily_spending(client, auth_header):
    """Daily spending breakdown is included with correct dates."""
    monday = _last_monday()
    tuesday = monday + timedelta(days=1)

    _create_expense(client, auth_header, 30, monday, "EXPENSE", "Mon spend")
    _create_expense(client, auth_header, 70, tuesday, "EXPENSE", "Tue spend")

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    daily = payload["daily_spending"]
    assert len(daily) == 2
    assert daily[0]["date"] == monday.isoformat()
    assert daily[0]["amount"] == 30.0
    assert daily[1]["date"] == tuesday.isoformat()
    assert daily[1]["amount"] == 70.0


def test_weekly_digest_custom_date(client, auth_header):
    """Digest accepts a custom reference date."""
    ref = date(2025, 3, 15)  # a Saturday
    r = client.get(f"/digest/weekly?date={ref.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    # ref is Saturday 2025-03-15, this_monday = 2025-03-10
    # previous full week: Mon 2025-03-03 to Sun 2025-03-09
    assert payload["period"]["start"] == "2025-03-03"
    assert payload["period"]["end"] == "2025-03-09"


def test_weekly_digest_invalid_date(client, auth_header):
    """Endpoint returns 400 for invalid date format."""
    r = client.get("/digest/weekly?date=not-a-date", headers=auth_header)
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_weekly_digest_empty_week(client, auth_header):
    """Digest gracefully handles weeks with no transactions."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["summary"]["total_income"] == 0.0
    assert payload["summary"]["total_expenses"] == 0.0
    assert payload["summary"]["net_flow"] == 0.0
    assert payload["summary"]["transaction_count"] == 0
    assert payload["category_breakdown"] == []
    assert payload["daily_spending"] == []
    assert len(payload["insights"]) > 0  # should still have generic insights


def test_weekly_digest_requires_auth(client):
    """Endpoint returns 401 without authentication."""
    r = client.get("/digest/weekly")
    assert r.status_code == 401
