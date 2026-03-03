"""Tests for the weekly financial digest feature (issue #121)."""

from datetime import date, timedelta


def _last_monday() -> date:
    """Return the Monday of the current ISO week."""
    today = date.today()
    return today - timedelta(days=today.weekday())


def test_weekly_digest_returns_required_fields(client, auth_header):
    """Digest endpoint returns all expected top-level keys."""
    monday = _last_monday()
    # Seed an expense this week
    r = client.post(
        "/expenses",
        json={
            "amount": 75.50,
            "description": "Weekly groceries",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    iso_year, iso_week, _ = monday.isocalendar()
    r = client.get(
        f"/insights/weekly-digest?year={iso_year}&week={iso_week}",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()

    required = {
        "week", "period", "income", "expenses", "net_flow",
        "transaction_count", "wow_change_pct", "previous_week_expenses",
        "top_categories", "daily_breakdown",
    }
    assert required.issubset(data.keys()), f"Missing: {required - data.keys()}"
    assert data["expenses"] >= 75.50
    assert data["transaction_count"] >= 1
    assert isinstance(data["top_categories"], list)
    assert isinstance(data["daily_breakdown"], list)


def test_weekly_digest_defaults_to_current_week(client, auth_header):
    """Omitting year/week params defaults to the current ISO week."""
    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    iso_year, iso_week, _ = date.today().isocalendar()
    assert data["week"] == f"{iso_year}-W{iso_week:02d}"


def test_weekly_digest_wow_change(client, auth_header):
    """Week-over-week change is calculated correctly."""
    monday = _last_monday()
    prev_monday = monday - timedelta(weeks=1)

    # Previous week: $200
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Prev week big spend",
            "date": prev_monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # This week: $100
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "This week moderate spend",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    iso_year, iso_week, _ = monday.isocalendar()
    r = client.get(
        f"/insights/weekly-digest?year={iso_year}&week={iso_week}",
        headers=auth_header,
    )
    data = r.get_json()
    # Expenses went from 200 → 100, so WoW = -50%
    assert data["wow_change_pct"] == -50.0
    assert data["previous_week_expenses"] == 200.0


def test_weekly_digest_empty_week(client, auth_header):
    """Digest for a week with no transactions returns zeros gracefully."""
    r = client.get(
        "/insights/weekly-digest?year=2020&week=1",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["expenses"] == 0
    assert data["income"] == 0
    assert data["transaction_count"] == 0
    assert data["top_categories"] == []
    assert data["daily_breakdown"] == []


def test_weekly_digest_includes_income(client, auth_header):
    """Income entries are tracked separately from expenses."""
    monday = _last_monday()

    client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Salary",
            "date": monday.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Lunch",
            "date": monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    iso_year, iso_week, _ = monday.isocalendar()
    r = client.get(
        f"/insights/weekly-digest?year={iso_year}&week={iso_week}",
        headers=auth_header,
    )
    data = r.get_json()
    assert data["income"] >= 500
    assert data["net_flow"] >= 450  # 500 - 50


def test_weekly_digest_gemini_fallback(client, auth_header, monkeypatch):
    """When Gemini is unavailable, method should be data_only."""
    def _boom(*a, **kw):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(
        "app.services.digest._gemini_narrative", _boom
    )

    r = client.get(
        "/insights/weekly-digest",
        headers={**auth_header, "X-Gemini-Api-Key": "fake-key"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["method"] == "data_only"
    assert data["narrative"] is None
    assert "gemini_unavailable" in data.get("warnings", [])
