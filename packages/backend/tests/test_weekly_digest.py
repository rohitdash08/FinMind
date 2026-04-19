from datetime import date, timedelta

def test_weekly_digest_returns_correct_fields(client, auth_header):
    # Setup: 2 transactions in current week, 1 in previous
    today = date.today()
    curr_date = today - timedelta(days=2)
    prev_date = today - timedelta(days=9)
    
    # Add a category first
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    cat_id = r.get_json()["id"]

    # Current week spend
    client.post("/expenses", json={
        "amount": 100,
        "category_id": cat_id,
        "description": "Lunch",
        "date": curr_date.isoformat(),
        "expense_type": "EXPENSE"
    }, headers=auth_header)

    # Previous week spend
    client.post("/expenses", json={
        "amount": 50,
        "category_id": cat_id,
        "description": "Old Lunch",
        "date": prev_date.isoformat(),
        "expense_type": "EXPENSE"
    }, headers=auth_header)

    # Fetch digest
    r = client.get(f"/insights/weekly-digest?date={today.isoformat()}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    
    assert "period" in payload
    assert payload["total_spend"] == 100
    assert payload["prev_total_spend"] == 50
    assert payload["total_change_pct"] == 100.0
    assert len(payload["significant_changes"]) > 0
    assert payload["significant_changes"][0]["category"] == "Food"
    assert payload["significant_changes"][0]["change_pct"] == 100.0

def test_weekly_digest_handles_empty_data(client, auth_header):
    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_spend"] == 0
    assert payload["prev_total_spend"] == 0
    assert payload["total_change_pct"] == 0
