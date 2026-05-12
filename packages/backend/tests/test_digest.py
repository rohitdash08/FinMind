"""Tests for weekly financial digest."""


def _auth_header(client):
    email = "digest@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def test_weekly_digest_empty(client):
    """Digest should work even with no data."""
    headers = _auth_header(client)
    r = client.get("/digest/weekly", headers=headers)
    assert r.status_code == 200
    digest = r.get_json()["digest"]
    assert "period" in digest
    assert "summary" in digest
    assert digest["summary"]["total_spent"] == 0
    assert digest["summary"]["transaction_count"] == 0
    assert "comparison" in digest
    assert "insights" in digest


def test_weekly_digest_with_date(client):
    """Digest should accept custom end_date."""
    headers = _auth_header(client)
    r = client.get("/digest/weekly?end_date=2026-05-12", headers=headers)
    assert r.status_code == 200
    digest = r.get_json()["digest"]
    assert digest["period"]["end"] == "2026-05-12"
    assert digest["period"]["start"] == "2026-05-05"


def test_digest_has_insights(client):
    """Digest should include insights array."""
    headers = _auth_header(client)
    r = client.get("/digest/weekly", headers=headers)
    digest = r.get_json()["digest"]
    assert isinstance(digest["insights"], list)
    # Should have the "no expenses" insight
    assert any("No expenses" in i for i in digest["insights"])
