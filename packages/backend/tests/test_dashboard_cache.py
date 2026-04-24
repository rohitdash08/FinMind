from datetime import date


def test_dashboard_cache_headers_and_invalidation(client, auth_header):
    month = date.today().strftime("%Y-%m")
    first = client.get(f"/dashboard/summary?month={month}", headers=auth_header)
    assert first.status_code == 200
    assert first.headers["X-FinMind-Cache"] in {"MISS", "HIT"}

    second = client.get(f"/dashboard/summary?month={month}", headers=auth_header)
    assert second.status_code == 200
    assert second.headers["X-FinMind-Cache"] == "HIT"

    created = client.post(
        "/expenses",
        json={
            "amount": 42,
            "description": "Cache invalidation expense",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert created.status_code == 201

    refreshed = client.get(f"/dashboard/summary?month={month}", headers=auth_header)
    assert refreshed.status_code == 200
    assert refreshed.headers["X-FinMind-Cache"] == "MISS"
    assert refreshed.get_json()["summary"]["monthly_expenses"] >= 42


def test_dashboard_cache_status_endpoint(client, auth_header):
    r = client.get("/dashboard/cache/status", headers=auth_header)
    assert r.status_code == 200
    stats = r.get_json()
    assert {"hits", "misses", "sets", "invalidations", "memory_keys"}.issubset(stats)
