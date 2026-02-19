"""Tests for the weekly digest endpoint."""


def _create_category(client, auth_header, name="Food"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    cats = r.get_json()
    return next(c["id"] for c in cats if c["name"] == name)


def _create_expense(client, auth_header, amount, category_id, date_str):
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "currency": "INR",
            "category_id": category_id,
            "description": "test",
            "date": date_str,
        },
        headers=auth_header,
    )
    assert r.status_code == 201


def test_weekly_digest_empty(client, auth_header):
    """Digest with no expenses returns zero totals."""
    r = client.get("/digest/weekly?week=2026-W08", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_spent"] == 0
    assert data["category_breakdown"] == {}
    assert data["week"] == "2026-W08"
    assert isinstance(data["trends"], list)
    assert isinstance(data["insights"], list)


def test_weekly_digest_with_expenses(client, auth_header):
    """Digest correctly aggregates expenses by category."""
    cat_id = _create_category(client, auth_header, "Food")
    cat_id2 = _create_category(client, auth_header, "Transport")

    # Week 8 of 2026: 2026-02-16 (Mon) to 2026-02-22 (Sun)
    _create_expense(client, auth_header, 100.0, cat_id, "2026-02-16")
    _create_expense(client, auth_header, 50.0, cat_id, "2026-02-18")
    _create_expense(client, auth_header, 200.0, cat_id2, "2026-02-17")

    r = client.get("/digest/weekly?week=2026-W08", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_spent"] == 350.0
    assert data["category_breakdown"]["Food"] == 150.0
    assert data["category_breakdown"]["Transport"] == 200.0
    assert len(data["trends"]) > 0


def test_weekly_digest_week_over_week(client, auth_header):
    """Digest computes week-over-week changes."""
    cat_id = _create_category(client, auth_header, "Food")

    # Week 7: 2026-02-09 to 2026-02-15
    _create_expense(client, auth_header, 100.0, cat_id, "2026-02-09")
    # Week 8: 2026-02-16 to 2026-02-22
    _create_expense(client, auth_header, 150.0, cat_id, "2026-02-16")

    r = client.get("/digest/weekly?week=2026-W08", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    wow = data["week_over_week_change"]
    assert "Food" in wow
    assert wow["Food"]["current"] == 150.0
    assert wow["Food"]["previous"] == 100.0
    assert wow["Food"]["change"] == 50.0


def test_weekly_digest_invalid_week(client, auth_header):
    """Invalid week format returns 400."""
    r = client.get("/digest/weekly?week=invalid", headers=auth_header)
    assert r.status_code == 400


def test_weekly_digest_requires_auth(client):
    """Endpoint requires JWT."""
    r = client.get("/digest/weekly")
    assert r.status_code == 401


def test_weekly_digest_default_week(client, auth_header):
    """Calling without week param returns current week."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "week" in data
    assert data["period"]["start"] is not None
