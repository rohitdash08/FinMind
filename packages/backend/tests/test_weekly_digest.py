from datetime import date, timedelta


def test_weekly_digest_returns_summary_fields(client, auth_header):
    """Test that weekly digest returns all required summary fields."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    # Add expenses for current week
    for i in range(3):
        r = client.post(
            "/expenses",
            json={
                "amount": 100 + i * 50,
                "description": f"Weekly expense {i}",
                "date": (monday + timedelta(days=i)).isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    # Add income for current week
    r = client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Weekly income",
            "date": monday.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Get weekly digest
    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # Check period
    assert "period" in payload
    assert "week_start" in payload["period"]
    assert "week_end" in payload["period"]

    # Check summary
    assert "summary" in payload
    assert "income" in payload["summary"]
    assert "expenses" in payload["summary"]
    assert "net_flow" in payload["summary"]
    assert "savings_rate_pct" in payload["summary"]
    assert "transaction_count" in payload["summary"]

    # Check trends
    assert "trends" in payload
    assert "week_over_week_change_pct" in payload["trends"]

    # Check categories
    assert "top_categories" in payload
    assert isinstance(payload["top_categories"], list)

    # Check tips
    assert "tips" in payload
    assert isinstance(payload["tips"], list)


def test_weekly_digest_with_reference_date(client, auth_header):
    """Test that weekly digest respects the reference_date parameter."""
    today = date.today()
    last_week_monday = today - timedelta(days=today.weekday() + 7)

    # Add expense for last week
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Last week expense",
            "date": last_week_monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Get weekly digest for last week
    r = client.get(
        f"/insights/weekly-digest?date={last_week_monday.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()

    # Check that the digest covers the correct week
    assert payload["summary"]["expenses"] == 200
    assert payload["summary"]["transaction_count"] == 1


def test_weekly_digest_week_over_week_comparison(client, auth_header):
    """Test that weekly digest calculates week-over-week change correctly."""
    today = date.today()
    this_week_monday = today - timedelta(days=today.weekday())
    last_week_monday = this_week_monday - timedelta(days=7)

    # Add expenses for last week
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Last week expense",
            "date": last_week_monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Add expenses for this week (50% increase)
    r = client.post(
        "/expenses",
        json={
            "amount": 150,
            "description": "This week expense",
            "date": this_week_monday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Get weekly digest for this week
    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # Check week-over-week change (should be +50%)
    assert payload["trends"]["week_over_week_change_pct"] == 50.0
    assert payload["trends"]["previous_week_expenses"] == 100


def test_weekly_digest_empty_data(client, auth_header):
    """Test that weekly digest handles empty data gracefully."""
    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    # Should return zero values for empty data
    assert payload["summary"]["income"] == 0
    assert payload["summary"]["expenses"] == 0
    assert payload["summary"]["transaction_count"] == 0
    assert payload["trends"]["week_over_week_change_pct"] == 0


def test_weekly_digest_invalid_date_format(client, auth_header):
    """Test that weekly digest returns 400 for invalid date format."""
    r = client.get("/insights/weekly-digest?date=invalid", headers=auth_header)
    assert r.status_code == 400
    payload = r.get_json()
    assert "error" in payload
