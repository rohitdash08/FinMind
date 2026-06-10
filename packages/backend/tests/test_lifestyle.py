from datetime import date, timedelta


def test_lifestyle_inflation(client, auth_header):
    today = date.today()
    # 30 days ago -> recent
    recent_date = today - timedelta(days=30)
    # 120 days ago -> past
    past_date = today - timedelta(days=120)

    # Past expenses (small)
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Dining Out Past",
            "date": past_date.isoformat(),
            "expense_type": "EXPENSE",
            "category_name": "Dining"
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Recent expenses (inflated)
    r = client.post(
        "/expenses",
        json={
            "amount": 300,
            "description": "Dining Out Recent",
            "date": recent_date.isoformat(),
            "expense_type": "EXPENSE",
            "category_name": "Dining"
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/insights/lifestyle-inflation", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["inflation_detected"] is True
    assert payload["recent_total"] == 300
    assert payload["past_total"] == 100
    assert payload["overall_increase_percentage"] == 200.0
    assert len(payload["driving_categories"]) == 1
    assert payload["driving_categories"][0]["category"] == "Dining"
    assert payload["driving_categories"][0]["increase_percentage"] == 200.0

def test_no_lifestyle_inflation(client, auth_header):
    today = date.today()
    # 30 days ago -> recent
    recent_date = today - timedelta(days=30)
    # 120 days ago -> past
    past_date = today - timedelta(days=120)

    # Past expenses
    r = client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Rent",
            "date": past_date.isoformat(),
            "expense_type": "EXPENSE",
            "category_name": "Housing"
        },
        headers=auth_header,
    )

    # Recent expenses
    r = client.post(
        "/expenses",
        json={
            "amount": 500,
            "description": "Rent",
            "date": recent_date.isoformat(),
            "expense_type": "EXPENSE",
            "category_name": "Housing"
        },
        headers=auth_header,
    )

    r = client.get("/insights/lifestyle-inflation", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["inflation_detected"] is False
    assert payload["overall_increase_percentage"] == 0.0
