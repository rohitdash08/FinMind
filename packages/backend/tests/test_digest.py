from datetime import date, timedelta


def test_weekly_digest_with_expenses(client, auth_header):
    today = date.today()
    r = client.post(
        "/expenses",
        json={
            "amount": 250,
            "description": "Groceries",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 1000,
            "description": "Salary",
            "date": today.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_expenses"] == 250.0
    assert payload["total_income"] == 1000.0
    assert payload["net"] == 750.0
    assert payload["daily_average"] == round(250.0 / 7, 2)
    assert payload["transactions_count"] == 2
    assert "period" in payload
    assert "narrative" in payload
    assert len(payload["top_categories"]) >= 0


def test_weekly_digest_empty_week(client, auth_header):
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_expenses"] == 0.0
    assert payload["total_income"] == 0.0
    assert payload["net"] == 0.0
    assert payload["transactions_count"] == 0
    assert payload["wow_change"] == 0.0
    assert "narrative" in payload


def test_weekly_digest_wow_comparison(client, auth_header):
    today = date.today()
    prev_date = today - timedelta(days=10)
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Previous week spend",
            "date": prev_date.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 300,
            "description": "Current week spend",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "wow_change" in payload
    assert isinstance(payload["wow_change"], float)


def test_preferences_default(client, auth_header):
    r = client.get("/digest/preferences", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["enabled"] is True
    assert payload["day_of_week"] == 0
    assert payload["send_email"] is True


def test_preferences_update(client, auth_header):
    r = client.put(
        "/digest/preferences",
        json={"enabled": False, "day_of_week": 4, "send_email": False},
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["enabled"] is False
    assert payload["day_of_week"] == 4
    assert payload["send_email"] is False

    r = client.get("/digest/preferences", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["enabled"] is False
    assert payload["day_of_week"] == 4


def test_preferences_invalid_day(client, auth_header):
    r = client.put(
        "/digest/preferences",
        json={"day_of_week": 7},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "day_of_week" in r.get_json()["error"]


def test_preferences_partial_update(client, auth_header):
    client.put(
        "/digest/preferences",
        json={"enabled": True, "day_of_week": 2, "send_email": True},
        headers=auth_header,
    )

    r = client.put(
        "/digest/preferences",
        json={"day_of_week": 5},
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["day_of_week"] == 5
    assert payload["enabled"] is True
    assert payload["send_email"] is True
