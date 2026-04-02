import pytest


def test_heatmap_daily_aggregation(client, auth_header):
    # Create some expenses
    for i in range(5):
        client.post(
            "/expenses",
            json={
                "amount": 10.0 * (i + 1),
                "description": f"Test expense {i}",
                "date": f"2026-01-{10 + i:02d}",
            },
            headers=auth_header,
        )
    
    r = client.get("/analytics/heatmap?year=2026&aggregation=daily", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    assert "data" in data
    assert "comparison" in data
    assert "metadata" in data
    
    assert data["metadata"]["year"] == 2026
    assert data["metadata"]["aggregation"] == "daily"
    
    # Check that we have daily entries
    assert len(data["data"]) >= 5
    
    # Check structure of first entry
    entry = data["data"][0]
    assert "date" in entry
    assert "amount" in entry
    assert "transaction_count" in entry
    assert "top_category" in entry


def test_heatmap_weekly_aggregation(client, auth_header):
    # Create expenses in different weeks
    dates = ["2026-01-05", "2026-01-06", "2026-01-12", "2026-01-15"]
    for i, d in enumerate(dates):
        client.post(
            "/expenses",
            json={
                "amount": 20.0 + i,
                "description": f"Weekly test {i}",
                "date": d,
            },
            headers=auth_header,
        )
    
    r = client.get("/analytics/heatmap?year=2026&aggregation=weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    assert data["metadata"]["aggregation"] == "weekly"
    
    # Check weekly structure
    if data["data"]:
        entry = data["data"][0]
        assert "week_start" in entry
        assert entry["date"].startswith("2026-W")


def test_heatmap_monthly_aggregation(client, auth_header):
    # Create expenses in different months
    dates = ["2026-01-15", "2026-01-20", "2026-02-10", "2026-03-05"]
    for i, d in enumerate(dates):
        client.post(
            "/expenses",
            json={
                "amount": 30.0 + i,
                "description": f"Monthly test {i}",
                "date": d,
            },
            headers=auth_header,
        )
    
    r = client.get("/analytics/heatmap?year=2026&aggregation=monthly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    assert data["metadata"]["aggregation"] == "monthly"
    
    # Should have entries for months with expenses
    months = [entry["date"] for entry in data["data"]]
    assert "2026-01" in months


def test_heatmap_with_category_filter(client, auth_header):
    # Create a category
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    cat_id = r.get_json()[0]["id"]
    
    # Create expenses with and without category
    client.post(
        "/expenses",
        json={
            "amount": 50.0,
            "description": "Categorized expense",
            "date": "2026-02-10",
            "category_id": cat_id,
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 100.0,
            "description": "Uncategorized expense",
            "date": "2026-02-11",
        },
        headers=auth_header,
    )
    
    r = client.get(f"/analytics/heatmap?year=2026&category={cat_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    # Only categorized expense should be included
    assert data["metadata"]["category_id"] == cat_id
    total = sum(entry["amount"] for entry in data["data"])
    assert total == 50.0


def test_heatmap_comparison(client, auth_header):
    # Create expenses in current year
    for i in range(3):
        client.post(
            "/expenses",
            json={
                "amount": 50.0,
                "description": f"Current year {i}",
                "date": f"2026-03-{10 + i:02d}",
            },
            headers=auth_header,
        )
    
    # Create expenses in previous year
    for i in range(2):
        client.post(
            "/expenses",
            json={
                "amount": 40.0,
                "description": f"Previous year {i}",
                "date": f"2025-03-{10 + i:02d}",
            },
            headers=auth_header,
        )
    
    r = client.get("/analytics/heatmap?year=2026", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    comparison = data["comparison"]
    assert "current_period_total" in comparison
    assert "previous_period_total" in comparison
    assert "change_amount" in comparison
    assert "change_percent" in comparison
    assert comparison["period_type"] == "year_over_year"
    
    assert comparison["current_period_total"] == 150.0
    assert comparison["previous_period_total"] == 80.0


def test_heatmap_invalid_year(client, auth_header):
    r = client.get("/analytics/heatmap?year=invalid", headers=auth_header)
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_heatmap_invalid_aggregation(client, auth_header):
    r = client.get("/analytics/heatmap?year=2026&aggregation=invalid", headers=auth_header)
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_heatmap_excludes_income(client, auth_header):
    # Create expense
    client.post(
        "/expenses",
        json={
            "amount": 100.0,
            "description": "Expense",
            "date": "2026-04-01",
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    
    # Create income (should be excluded)
    client.post(
        "/expenses",
        json={
            "amount": 1000.0,
            "description": "Income",
            "date": "2026-04-02",
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    
    r = client.get("/analytics/heatmap?year=2026&aggregation=daily", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    total = sum(entry["amount"] for entry in data["data"])
    # Income should not be counted
    assert total == 100.0


def test_heatmap_top_category(client, auth_header):
    # Create categories
    r = client.post("/categories", json={"name": "Groceries"}, headers=auth_header)
    r = client.get("/categories", headers=auth_header)
    groceries_id = [c["id"] for c in r.get_json() if c["name"] == "Groceries"][0]
    
    r = client.post("/categories", json={"name": "Transport"}, headers=auth_header)
    r = client.get("/categories", headers=auth_header)
    transport_id = [c["id"] for c in r.get_json() if c["name"] == "Transport"][0]
    
    # Create multiple expenses on same day with different categories
    client.post(
        "/expenses",
        json={
            "amount": 100.0,
            "description": "Groceries",
            "date": "2026-05-01",
            "category_id": groceries_id,
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 30.0,
            "description": "Transport",
            "date": "2026-05-01",
            "category_id": transport_id,
        },
        headers=auth_header,
    )
    
    r = client.get("/analytics/heatmap?year=2026&aggregation=daily", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    
    # Find the entry for 2026-05-01
    may01_entry = next((e for e in data["data"] if e["date"] == "2026-05-01"), None)
    assert may01_entry is not None
    assert may01_entry["top_category"] == "Groceries"
    assert may01_entry["transaction_count"] == 2


def test_heatmap_unauthenticated(client):
    r = client.get("/analytics/heatmap?year=2026")
    assert r.status_code == 401
