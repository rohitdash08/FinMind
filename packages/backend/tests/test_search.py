from datetime import date, timedelta


def test_search_returns_transactions_and_bills(client, auth_header):
    today = date.today()

    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Test transaction search",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/bills",
        json={
            "name": "Test Bill Search",
            "amount": 200,
            "next_due_date": (today + timedelta(days=5)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/search?q=test&type=all", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert isinstance(payload["transactions"], list)
    assert isinstance(payload["bills"], list)
    assert payload["total_count"] >= 1


def test_search_filters_by_date_range(client, auth_header):
    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Date filtered expense",
            "date": "2026-01-15",
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        "/search?from=2026-01-01&to=2026-01-31&type=transactions",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert len(payload["transactions"]) >= 1


def test_search_filters_by_amount_range(client, auth_header):
    r = client.post(
        "/expenses",
        json={
            "amount": 75,
            "description": "Amount filtered expense",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        "/search?amount_min=50&amount_max=100&type=transactions",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert len(payload["transactions"]) >= 1


def test_search_empty_query_returns_all(client, auth_header):
    r = client.get("/search?q=&type=all", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert isinstance(payload["transactions"], list)
    assert isinstance(payload["bills"], list)
