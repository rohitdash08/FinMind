from datetime import date, timedelta


def _this_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _this_sunday() -> date:
    return _this_monday() + timedelta(days=6)


def _last_monday() -> date:
    return _this_monday() - timedelta(days=7)


def test_weekly_digest_empty_week(client, auth_header):
    """Digest for a week with no data returns zeros."""
    monday = _this_monday()
    r = client.get(f"/digests/weekly?week={monday.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_income"] == 0.0
    assert data["total_expenses"] == 0.0
    assert data["net_savings"] == 0.0
    assert data["bills_due_count"] == 0
    assert data["week_start"] == monday.isoformat()
    assert data["week_end"] == _this_sunday().isoformat()


def test_weekly_digest_with_income_and_expenses(client, auth_header):
    """Digest aggregates income vs expenses correctly."""
    monday = _this_monday()
    tuesday = monday + timedelta(days=1)

    # Create a category
    r = client.post("/categories", json={"name": "Groceries"}, headers=auth_header)
    assert r.status_code == 201
    cat_id = r.get_json()["id"]

    # Income
    r = client.post(
        "/expenses",
        json={
            "amount": 5000,
            "description": "Salary",
            "date": monday.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Expense in Groceries
    r = client.post(
        "/expenses",
        json={
            "amount": 300,
            "description": "Weekly groceries",
            "date": tuesday.isoformat(),
            "expense_type": "EXPENSE",
            "category_id": cat_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(f"/digests/weekly?week={monday.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_income"] == 5000.0
    assert data["total_expenses"] == 300.0
    assert data["net_savings"] == 4700.0
    assert data["top_category"] == "Groceries"
    assert data["top_expense_amount"] == 300.0
    assert data["summary_text"] is not None
    assert "Groceries" in data["summary_text"]


def test_weekly_digest_default_current_week(client, auth_header):
    """GET /digests/weekly without ?week returns current week digest."""
    r = client.get("/digests/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "week_start" in data
    assert "week_end" in data


def test_weekly_digest_bills_due(client, auth_header):
    """Bills due this week are counted."""
    monday = _this_monday()
    wednesday = monday + timedelta(days=2)

    r = client.post(
        "/bills",
        json={
            "name": "Electricity",
            "amount": 120.50,
            "next_due_date": wednesday.isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(f"/digests/weekly?week={monday.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["bills_due_count"] >= 1


def test_weekly_digest_wow_change(client, auth_header):
    """Week-over-week change is computed when previous week has data."""
    monday = _this_monday()
    last_monday = _last_monday()
    last_tuesday = last_monday + timedelta(days=1)
    tuesday = monday + timedelta(days=1)

    # Previous week expense
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Last week spend",
            "date": last_tuesday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Current week expense
    r = client.post(
        "/expenses",
        json={
            "amount": 400,
            "description": "This week spend",
            "date": tuesday.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(f"/digests/weekly?week={monday.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    # 400 vs 200 = 100% increase
    assert data["wow_expense_change_pct"] == 100.0


def test_weekly_digest_invalid_week_param(client, auth_header):
    """Invalid week param returns 400."""
    r = client.get("/digests/weekly?week=not-a-date", headers=auth_header)
    assert r.status_code == 400


def test_digest_history(client, auth_header):
    """History endpoint returns list of past digests."""
    monday = _this_monday()
    # Generate at least one digest
    r = client.get(f"/digests/weekly?week={monday.isoformat()}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/digests/history", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["week_start"] == monday.isoformat()


def test_digest_history_limit(client, auth_header):
    """History endpoint respects limit param."""
    r = client.get("/digests/history?limit=5", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) <= 5


def test_weekly_digest_idempotent(client, auth_header):
    """Calling digest twice for the same week updates, not duplicates."""
    monday = _this_monday()
    r1 = client.get(f"/digests/weekly?week={monday.isoformat()}", headers=auth_header)
    assert r1.status_code == 200
    id1 = r1.get_json()["id"]

    r2 = client.get(f"/digests/weekly?week={monday.isoformat()}", headers=auth_header)
    assert r2.status_code == 200
    id2 = r2.get_json()["id"]
    assert id1 == id2
