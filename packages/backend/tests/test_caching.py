"""Tests for smart in-memory caching strategy (Issue #127)."""

from datetime import date, timedelta


def test_dashboard_returns_x_cache_hit_header(client, auth_header):
    """First call should be a miss, second call should be a hit."""
    # Seed some data so the response is non-trivial
    client.post(
        "/expenses",
        json={"amount": 100, "description": "Test", "date": date.today().isoformat()},
        headers=auth_header,
    )

    # First call - cache miss
    r1 = client.get("/dashboard/summary", headers=auth_header)
    assert r1.status_code == 200
    assert r1.headers.get("X-Cache-Hit") == "false"

    # Second call - cache hit
    r2 = client.get("/dashboard/summary", headers=auth_header)
    assert r2.status_code == 200
    assert r2.headers.get("X-Cache-Hit") == "true"


def test_dashboard_cache_invalidated_on_expense_create(client, auth_header):
    """Creating an expense should invalidate the dashboard cache."""
    # Warm the cache
    client.get("/dashboard/summary", headers=auth_header)
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "true"

    # Create expense - should invalidate
    client.post(
        "/expenses",
        json={"amount": 50, "description": "Invalidator", "date": date.today().isoformat()},
        headers=auth_header,
    )

    # Next call should be a miss
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "false"


def test_dashboard_cache_invalidated_on_expense_update(client, auth_header):
    """Updating an expense should invalidate the cache."""
    r = client.post(
        "/expenses",
        json={"amount": 75, "description": "Updatable", "date": date.today().isoformat()},
        headers=auth_header,
    )
    expense_id = r.get_json()["id"]

    # Warm cache
    client.get("/dashboard/summary", headers=auth_header)
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "true"

    # Update expense
    client.patch(
        f"/expenses/{expense_id}",
        json={"amount": 150},
        headers=auth_header,
    )

    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "false"


def test_dashboard_cache_invalidated_on_expense_delete(client, auth_header):
    """Deleting an expense should invalidate the cache."""
    r = client.post(
        "/expenses",
        json={"amount": 25, "description": "Deletable", "date": date.today().isoformat()},
        headers=auth_header,
    )
    expense_id = r.get_json()["id"]

    # Warm cache
    client.get("/dashboard/summary", headers=auth_header)
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "true"

    # Delete expense
    client.delete(f"/expenses/{expense_id}", headers=auth_header)

    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "false"


def test_dashboard_cache_invalidated_on_bill_create(client, auth_header):
    """Creating a bill should invalidate the cache."""
    # Warm cache
    client.get("/dashboard/summary", headers=auth_header)
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "true"

    # Create bill
    client.post(
        "/bills",
        json={
            "name": "Phone",
            "amount": 30,
            "next_due_date": (date.today() + timedelta(days=5)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )

    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "false"


def test_dashboard_cache_invalidated_on_category_crud(client, auth_header):
    """Category CRUD should invalidate the cache."""
    # Warm cache
    client.get("/dashboard/summary", headers=auth_header)
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "true"

    # Create category
    r = client.post("/categories", json={"name": "TestCat"}, headers=auth_header)
    assert r.status_code == 201
    cat_id = r.get_json()["id"]

    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "false"

    # Warm cache again
    client.get("/dashboard/summary", headers=auth_header)
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "true"

    # Update category
    client.patch(f"/categories/{cat_id}", json={"name": "UpdatedCat"}, headers=auth_header)
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "false"

    # Warm cache again
    client.get("/dashboard/summary", headers=auth_header)
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "true"

    # Delete category
    client.delete(f"/categories/{cat_id}", headers=auth_header)
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "false"


def test_different_month_params_cached_separately(client, auth_header):
    """Different month query params should produce separate cache entries."""
    month_a = date.today().strftime("%Y-%m")
    month_b = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    # Warm cache for month_a
    client.get(f"/dashboard/summary?month={month_a}", headers=auth_header)
    r = client.get(f"/dashboard/summary?month={month_a}", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "true"

    # month_b should still be a miss
    r = client.get(f"/dashboard/summary?month={month_b}", headers=auth_header)
    assert r.headers.get("X-Cache-Hit") == "false"
