from datetime import date, timedelta


def _add_expense(client, auth_header, amount, spent_at, expense_type="EXPENSE"):
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "description": f"Test {expense_type}",
            "date": spent_at.isoformat(),
            "expense_type": expense_type,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()


def test_weekly_digest_empty(client, auth_header):
    """Digest with no data returns valid structure."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "week" in data
    assert "summary" in data
    assert "comparison" in data
    assert "highlights" in data
    assert data["summary"]["total_spending"] == 0
    assert data["summary"]["total_income"] == 0
    assert data["summary"]["transaction_count"] == 0


def test_weekly_digest_with_expenses(client, auth_header):
    """Digest reflects expenses added in the current week."""
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()

    # Ensure we add on a weekday within the current ISO week
    monday = today - timedelta(days=today.weekday())
    _add_expense(client, auth_header, 50, monday)
    _add_expense(client, auth_header, 30, monday + timedelta(days=1))
    _add_expense(client, auth_header, 100, monday, expense_type="INCOME")

    r = client.get(
        f"/digest/weekly?year={iso_year}&week={iso_week}",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["total_spending"] == 80
    assert data["summary"]["total_income"] == 100
    assert data["summary"]["net_flow"] == 20
    assert data["summary"]["transaction_count"] == 3


def test_weekly_digest_week_over_week(client, auth_header):
    """Digest computes week-over-week change correctly."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    prev_monday = monday - timedelta(weeks=1)

    iso_year, iso_week, _ = monday.isocalendar()

    # Previous week: $100 spending
    _add_expense(client, auth_header, 100, prev_monday)
    # Current week: $150 spending
    _add_expense(client, auth_header, 150, monday)

    r = client.get(
        f"/digest/weekly?year={iso_year}&week={iso_week}",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["comparison"]["week_over_week_change_pct"] == 50.0
    assert data["comparison"]["previous_spending"] == 100


def test_weekly_digest_partial_params_rejected(client, auth_header):
    """Providing only year or only week returns 400."""
    r = client.get("/digest/weekly?year=2026", headers=auth_header)
    assert r.status_code == 400

    r = client.get("/digest/weekly?week=10", headers=auth_header)
    assert r.status_code == 400


def test_weekly_digest_requires_auth(client):
    """Unauthenticated request returns 401."""
    r = client.get("/digest/weekly")
    assert r.status_code == 401
